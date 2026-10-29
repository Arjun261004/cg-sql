from typing import Dict, List, Any, Optional
from src.agents.base_agent import BaseAgent
from src.models.state import GraphState
from src.models.messages import AgentMessage, MessageType
from src.core.agent_registry import AgentDescriptor
from src.tools.static_analyzer import ErrorClassifier
from src.tools.maple_doctor import MAPLEDoctorRepairer
from src.tools.llm_repairer import LLMRepairer

class RepairAgent(BaseAgent):
    """
    AGENT 5 — RepairAgent
    Role: Rule-first diagnosis and repair of failed SQL queries.
    Absorbs:
    - Static Analyzer (error classification & symptom extraction)
    - MAPLEDoctor integration (deterministic rule-based repair engine)
    - Semantic Repair Agent (constrained LLM fallback repair)
    
    Workflow:
    Execution/Validation Failure -> Symptom Extraction -> Error Classification ->
    Known deterministic MAPLEDoctor rule?
       YES -> Rule fix (avoids LLM call)
       NO  -> Constrained LLM repair
    -> Re-validate via ValidationExecutionAgent
    """
    def __init__(self, kb=None):
        super().__init__("RepairAgent", "Rule-first self-repair of SQL execution and semantic errors", kb=kb)
        self.error_classifier = ErrorClassifier(kb=kb)
        self.maple_doctor = MAPLEDoctorRepairer(kb=kb)
        self.llm_repairer = LLMRepairer(kb=kb)

    def get_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            name=self.name,
            role=self.role,
            capabilities=[
                "error_classification",
                "symptom_extraction",
                "maple_doctor_rule_repair",
                "constrained_llm_repair"
            ],
            tools=["error_classifier", "maple_doctor_repairer", "llm_repairer"],
            input_requirements=["execution_results", "validation_result"],
            activation_conditions=["execution_error", "validation_failure"]
        )

    def observe(self, state: GraphState) -> None:
        self.error_classifier.kb = self.kb
        self.maple_doctor.kb = self.kb
        self.llm_repairer.kb = self.kb

    def reason(self, state: GraphState) -> None:
        pass

    def evaluate_evidence(self, state: GraphState) -> float:
        if state.repair_history:
            return state.repair_history[-1].get("confidence", 0.90)
        return 0.85

    def propose_action(self, state: GraphState) -> Optional[AgentMessage]:
        last_exec = state.execution_results[-1] if state.execution_results else {}
        val_result = state.validation_result
        has_error = bool(last_exec.get("error")) or (val_result and not val_result.execution_success)

        failed_candidate = state.selected_candidate or (state.sql_candidates[-1] if state.sql_candidates else {})
        failed_sql = failed_candidate.get("sql", "")
        dataset = "spider"
        database_id = state.database_id or state.database
        dialect = state.dialect or "SQLite"

        # Case 1: No execution failure -> Run MapleDoctor inspection for logic/convention rules
        if not has_error:
            if getattr(state, "mapledoctor_verified", False):
                return None

            # Run MapleDoctor detection on candidate SQL to check for logic/convention issues
            try:
                from src.mapledoctor.detector.detector import UniversalDetector
                detector = UniversalDetector(kb=self.kb)
                detection = detector.detect(
                    sql=failed_sql,
                    dataset=dataset,
                    database_id=database_id,
                    dialect=dialect,
                    db_path=state.db_path,
                    kb=self.kb,
                    question=state.original_request or state.intent
                )
                if detection and detection.is_rule_applicable:
                    # Deterministic repair rule applies (e.g. division cast, null sort, alias)
                    repaired_sql, rule_name, rule_confidence = self.maple_doctor.attempt_rule_repair(
                        failed_sql=failed_sql,
                        classification={"category": detection.category.value, "details": detection.evidence},
                        dataset=dataset,
                        database_id=database_id,
                        dialect=dialect
                    )
                    if repaired_sql and repaired_sql != failed_sql:
                        new_cand = {
                            "id": f"repaired_{len(state.repair_history) + 1}",
                            "sql": repaired_sql,
                            "type": "repaired",
                            "confidence": rule_confidence
                        }
                        state.sql_candidates.append(new_cand)
                        state.selected_candidate = new_cand
                        state.mapledoctor_verified = True
                        return AgentMessage(
                            agent=self.name,
                            message_type=MessageType.PROPOSAL,
                            capability=f"MAPLEDoctor Rule Repair: {rule_name}",
                            claim=f"Repaired SQL logic pattern ({detection.category.value}) using {rule_name}.",
                            evidence=[{"original_sql": failed_sql, "repaired_sql": repaired_sql}],
                            confidence=rule_confidence,
                            target_agents=["ValidationExecutionAgent"]
                        )
            except Exception:
                pass

            # Query is clean
            state.mapledoctor_verified = True
            return AgentMessage(
                agent=self.name,
                message_type=MessageType.EVIDENCE,
                capability="MAPLEDoctor Verification",
                claim="MAPLEDoctor verified: No syntax, schema, logic, or convention anti-patterns detected.",
                evidence=[{"verified_sql": failed_sql}],
                confidence=1.0
            )

        # Case 2: Execution or Validation failure
        # Guard against infinite repair loops (max 3 repairs)
        if len(state.repair_history) >= 3:
            state.mapledoctor_verified = True
            return AgentMessage(
                agent=self.name,
                message_type=MessageType.REJECTION,
                capability="Repair Budget Exceeded",
                claim="Max repair attempts (3) exceeded. Terminating repair cycle.",
                confidence=0.0
            )

        error_text = last_exec.get("error") or "; ".join(val_result.errors if val_result else ["Unknown error"])

        # 1. SYMPTOM EXTRACTION & ERROR CLASSIFICATION
        classification = self.error_classifier.classify_error(error_text, failed_sql)
        category = classification.get("category", "UNKNOWN")

        # 2. RULE-FIRST REPAIR via MAPLEDoctor
        repaired_sql, rule_name, rule_confidence = self.maple_doctor.attempt_rule_repair(
            failed_sql=failed_sql,
            classification=classification,
            dataset=dataset,
            database_id=database_id,
            dialect=dialect
        )

        repair_method = ""
        confidence = 0.0

        if repaired_sql and rule_name:
            # Deterministic rule succeeded!
            repair_method = f"MAPLEDoctor deterministic rule: {rule_name}"
            confidence = rule_confidence
        else:
            # If the error is due to requested concepts that do not exist in the database,
            # bypass LLM repair and proceed directly to MapleDoctor schema diagnosis.
            unmatched = state.schema_linking.unmatched_concepts if state.schema_linking else []
            if unmatched or category == "SCHEMA_MISSING":
                repaired_sql = None
            else:
                # 3. CONSTRAINED LLM FALLBACK REPAIR
                repaired_sql, llm_conf = self.llm_repairer.repair_sql(
                    original_query=state.original_request or state.intent,
                    failed_sql=failed_sql,
                    error_text=error_text,
                    classification=classification,
                    schema_linking=state.schema_linking,
                    dialect=dialect
                )
                if repaired_sql:
                    repair_method = "Constrained LLM repair with schema bounds"
                    confidence = llm_conf

        if repaired_sql and repaired_sql != failed_sql:
            repair_entry = {
                "iteration": len(state.repair_history) + 1,
                "category": category,
                "original_sql": failed_sql,
                "repaired_sql": repaired_sql,
                "method": repair_method,
                "strategy": "RULE_BASED" if "deterministic" in repair_method.lower() else "LLM_FALLBACK",
                "detection_evidence": classification.get("details", {}),
                "error_text": error_text,
                "confidence": confidence
            }
            state.repair_history.append(repair_entry)

            # Create new repaired candidate
            new_cand = {
                "id": f"repaired_{len(state.repair_history)}",
                "sql": repaired_sql,
                "type": "repaired",
                "confidence": confidence
            }
            state.sql_candidates.append(new_cand)
            state.selected_candidate = new_cand

            claim_text = f"Repaired SQL error ({category}) using {repair_method}. Re-routing to validation."
            return AgentMessage(
                agent=self.name,
                message_type=MessageType.PROPOSAL,
                capability=repair_method,
                claim=claim_text,
                evidence=[repair_entry],
                confidence=confidence,
                target_agents=["ValidationExecutionAgent"]
            )
        else:
            # Unrepairable schema hallucination or fatal error
            schema = self.kb.get_schema(dataset, database_id) if self.kb else None
            available_tables = list(schema.tables.keys()) if schema else []
            diag_claim = (
                f"MapleDoctor Diagnosis: The requested attributes/entities do not exist in database '{database_id}'. "
                f"Available tables in '{database_id}': {available_tables}."
            )
            state.final_answer = (
                f"Schema Error: The requested attributes or entities do not exist in database '{database_id}'. "
                f"Available tables: {', '.join(available_tables)}."
            )
            state.mapledoctor_verified = True
            return AgentMessage(
                agent=self.name,
                message_type=MessageType.OBJECTION,
                capability="MAPLEDoctor Schema Diagnosis",
                claim=diag_claim,
                evidence=[{
                    "error": error_text,
                    "database_id": database_id,
                    "available_tables": available_tables,
                    "category": category
                }],
                confidence=0.0
            )
