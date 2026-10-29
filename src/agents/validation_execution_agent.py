from typing import Dict, List, Any, Optional
from src.agents.base_agent import BaseAgent
from src.models.state import GraphState, ValidationResult
from src.models.messages import AgentMessage, MessageType
from src.core.agent_registry import AgentDescriptor
from src.tools.static_analyzer import StaticValidator
from src.tools.sql_critic import SQLCritic
from src.tools.database_executor import DatabaseExecutor
from src.tools.semantic_verifier import SemanticVerifier

class ValidationExecutionAgent(BaseAgent):
    """
    AGENT 4 — ValidationExecutionAgent
    Role: Static validation, dynamic execution, and semantic verification.
    Absorbs:
    - Execution Agent (dynamic SQLite & DuckDB execution)
    - Critic Agent (pre-execution SQL critique & adversarial checks)
    - Judge Agent (semantic result validation & intent alignment)
    - Static Validator (table/column existence checks against KB)
    """
    def __init__(self, kb=None):
        super().__init__("ValidationExecutionAgent", "Static validation, database execution, and semantic verification", kb=kb)
        self.static_validator = StaticValidator(kb=kb)
        self.sql_critic = SQLCritic(kb=kb)
        self.executor = DatabaseExecutor(kb=kb)
        self.verifier = SemanticVerifier()

    def get_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            name=self.name,
            role=self.role,
            capabilities=[
                "static_sql_validation",
                "adversarial_critique",
                "database_execution",
                "semantic_verification"
            ],
            tools=["static_validator", "sql_critic", "database_executor", "semantic_verifier"],
            input_requirements=["sql_candidates"],
            activation_conditions=["unvalidated_candidates"]
        )

    def observe(self, state: GraphState) -> None:
        self.static_validator.kb = self.kb
        self.sql_critic.kb = self.kb
        self.executor.kb = self.kb

    def reason(self, state: GraphState) -> None:
        pass

    def evaluate_evidence(self, state: GraphState) -> float:
        if state.validation_result:
            return state.validation_result.confidence
        return 0.85

    def propose_action(self, state: GraphState) -> Optional[AgentMessage]:
        if not state.selected_candidate and state.sql_candidates:
            state.selected_candidate = state.sql_candidates[-1]

        if not state.selected_candidate:
            return None

        sql = state.selected_candidate.get("sql", "").strip()
        dataset = "spider"
        database_id = state.database_id or state.database
        dialect = state.dialect or "SQLite"

        # 1. STATIC VALIDATION: Check schema existence via KB
        static_res = self.static_validator.validate_sql(
            sql=sql,
            dataset=dataset,
            database_id=database_id,
            schema_linking=state.schema_linking
        )

        # 2. ADVERSARIAL CRITIQUE: Check SQL rules & dialect violations
        dialect_rules = state.knowledge_context.get("dialect_rules")
        critic_res = self.sql_critic.critique(
            sql=sql,
            dialect=dialect,
            dialect_rules=dialect_rules,
            schema_linking=state.schema_linking
        )

        # If static validation or critique detected severe fatal issues
        fatal_errors = static_res.get("errors", []) + critic_res.get("issues", [])
        if fatal_errors:
            exec_dict = {
                "status": "error",
                "error": "; ".join(fatal_errors),
                "rows": 0,
                "columns": [],
                "data": []
            }
        else:
            # 3. DYNAMIC EXECUTION: Execute query against database engine adapter
            exec_dict = self.executor.execute(
                sql=sql,
                dialect=dialect,
                db_path=state.db_path,
                dataset=dataset,
                database_id=database_id
            )

        # 4. SEMANTIC VERIFICATION: Evaluate results against conceptual intent
        val_result = self.verifier.verify(
            executed_sql=sql,
            execution_dict=exec_dict,
            concept_grounding=state.concept_grounding,
            schema_linking=state.schema_linking
        )
        # Append any critic warnings
        val_result.warnings.extend(critic_res.get("warnings", []))

        # Store on blackboard
        state.validation_result = val_result
        state.execution_results.append(exec_dict)
        state.selected_candidate["validation"] = val_result.dict()

        if val_result.execution_success and val_result.semantic_correctness:
            claim_text = (
                f"SQL executed and semantically verified: {val_result.row_count} rows, "
                f"status={val_result.verification_status}."
            )
            return AgentMessage(
                agent=self.name,
                message_type=MessageType.EVIDENCE,
                capability="Static Validation & Semantic Execution",
                claim=claim_text,
                evidence=[val_result.dict()],
                confidence=val_result.confidence
            )
        else:
            err_msg = "; ".join(val_result.errors) if val_result.errors else "; ".join(val_result.warnings)
            claim_text = f"Validation failed: {err_msg}"
            return AgentMessage(
                agent=self.name,
                message_type=MessageType.OBJECTION,
                capability="Static Validation & Semantic Execution",
                claim=claim_text,
                evidence=[val_result.dict()],
                confidence=0.10
            )
