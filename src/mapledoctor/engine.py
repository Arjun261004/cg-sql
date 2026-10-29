import logging
from typing import Optional, Dict, Any, List
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import (
    ErrorCategory,
    DetectionResult,
    RepairStrategy,
    RepairAttempt,
    MapleDoctorResult
)
from src.mapledoctor.detector.detector import UniversalDetector
from src.mapledoctor.repair.hybrid_repairer import HybridRepairer
from src.mapledoctor.validator.repair_validator import RepairValidator
from src.mapledoctor.probes import DatabaseProber

logger = logging.getLogger("MapleDoctor")

class MapleDoctorEngine:
    """
    MapleDoctor SQL Error Detection and Repair Engine.
    Implements the complete methodology from:
    'Understanding, Detecting, and Repairing Real-World In-Context-Learning-Based Text-to-SQL Errors'
    (Shen et al., Proc. ACM Softw. Eng., FSE, 2026).
    
    Features:
    - Rule-First Hybrid Repair Strategy (deterministic rules before LLM)
    - Execution-First Priority (Syntax -> Schema -> Logic -> Convention -> Symptoms)
    - Iterative multi-error repair loop
    - Mis-repair safety guards
    - Safe non-executable termination behavior (reverts to original query)
    - Full traceability & diagnostics logging
    """

    def __init__(
        self,
        kb: Optional[KnowledgeBase] = None,
        executor: Optional[Any] = None,
        llm_client: Optional[Any] = None
    ):
        self.kb = kb
        if executor is None:
            from src.tools.database_executor import DatabaseExecutor
            self.executor = DatabaseExecutor(kb=kb)
        else:
            self.executor = executor
        self.prober = DatabaseProber(executor=self.executor)
        self.detector = UniversalDetector(kb=kb, prober=self.prober)
        self.repairer = HybridRepairer(kb=kb, llm_client=llm_client)
        self.validator = RepairValidator(executor=self.executor, kb=kb)

    def diagnose_and_repair(
        self,
        sql: str,
        question: str = "",
        error_text: Optional[str] = None,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        db_path: str = "",
        execution_dict: Optional[Dict[str, Any]] = None,
        max_repairs: int = 3
    ) -> MapleDoctorResult:
        """
        Main entry point for MapleDoctor detection and repair.
        Runs post-generation detection, iterative hybrid repair, validation, and safe termination.
        """
        trace: List[str] = []
        repair_history: List[RepairAttempt] = []
        current_sql = sql.strip()

        # Step 0: Dry-run execution if no execution result was passed
        current_exec = execution_dict
        current_err = error_text
        if not current_exec and not current_err:
            current_exec = self.executor.execute(
                sql=current_sql,
                dialect=dialect,
                db_path=db_path,
                dataset=dataset,
                database_id=database_id
            )
            if current_exec.get("status") == "error":
                current_err = current_exec.get("error")

        # Step 1: Initial Error Detection
        detection = self.detector.detect(
            sql=current_sql,
            error_text=current_err,
            dataset=dataset,
            database_id=database_id,
            dialect=dialect,
            db_path=db_path,
            execution_dict=current_exec,
            question=question
        )

        if not detection:
            # No error detected -> Pass through cleanly!
            trace.append("MapleDoctor: No errors detected. SQL query is sound.")
            return MapleDoctorResult(
                original_sql=sql,
                final_sql=sql,
                was_repaired=False,
                error_detected=False,
                iterations=0,
                is_executable=(current_exec.get("status") == "success") if current_exec else True,
                final_execution_data=current_exec,
                trace=trace
            )

        # Error was detected!
        initial_detection = detection
        trace.append(f"MapleDoctor DETECTED: [{detection.category.value}] {detection.description}")

        # Step 2: Iterative Repair Loop
        iteration = 0
        final_executable = False

        while iteration < max_repairs and detection:
            iteration += 1
            trace.append(f"MapleDoctor Iteration {iteration}: Repairing [{detection.category.value}] via {detection.rule_name or 'LLM'}")

            # Apply Rule-First Hybrid Repair
            repaired_sql, strategy, rule_or_method, conf = self.repairer.repair(
                sql=current_sql,
                detection=detection,
                question=question,
                dataset=dataset,
                database_id=database_id,
                dialect=dialect
            )

            if not repaired_sql:
                trace.append(f"MapleDoctor: Repair failed at iteration {iteration}. No viable fix found.")
                break

            # Validate the repair with re-execution and mis-repair safety checks
            validation = self.validator.validate_repair(
                original_sql=current_sql,
                repaired_sql=repaired_sql,
                original_detection=detection,
                dialect=dialect,
                db_path=db_path,
                dataset=dataset,
                database_id=database_id
            )

            # Record repair attempt
            attempt = RepairAttempt(
                iteration=iteration,
                category=detection.category,
                strategy=strategy,
                rule_name=rule_or_method,
                original_sql=current_sql,
                repaired_sql=repaired_sql,
                confidence=conf,
                explanation=f"Repaired {detection.category.value} via {strategy.value} ({rule_or_method})",
                re_execution_result=validation.execution_dict,
                success=validation.is_valid,
                remaining_error=validation.remaining_error
            )
            repair_history.append(attempt)

            trace.append(
                f"MapleDoctor Attempt {iteration}: Strategy={strategy.value}, Valid={validation.is_valid}, "
                f"Executable={validation.is_executable}, Error={validation.remaining_error}"
            )

            if validation.is_valid:
                current_sql = repaired_sql
                current_exec = validation.execution_dict
                final_executable = True

                # Check if another error remains in current_sql (iterative multiple-error handling)
                detection = self.detector.detect(
                    sql=current_sql,
                    error_text=None,
                    dataset=dataset,
                    database_id=database_id,
                    dialect=dialect,
                    db_path=db_path,
                    execution_dict=current_exec,
                    question=question
                )
                if not detection:
                    trace.append("MapleDoctor: All detected errors successfully resolved.")
                    break
                else:
                    trace.append(f"MapleDoctor: Secondary error detected: [{detection.category.value}] {detection.description}")
            else:
                # Validation failed
                if validation.is_executable:
                    current_sql = repaired_sql
                    current_exec = validation.execution_dict
                    final_executable = True
                    break
                else:
                    # Re-execution threw error, prepare next iteration with new error text
                    current_err = validation.remaining_error
                    detection = self.detector.detect(
                        sql=repaired_sql,
                        error_text=current_err,
                        dataset=dataset,
                        database_id=database_id,
                        dialect=dialect,
                        db_path=db_path,
                        execution_dict=validation.execution_dict,
                        question=question
                    )
                    current_sql = repaired_sql

        # Step 3: Termination behavior
        # Paper explicitly specifies:
        # "If the query remains non-executable after the available repair process:
        #  terminate the MapleDoctor repair process and return the original query
        #  according to the paper's described behavior."
        final_sql = current_sql
        termination_reason = None
        if not final_executable:
            # Check if original was executable or if repaired query is broken
            orig_check = self.executor.execute(sql=sql, dialect=dialect, db_path=db_path, dataset=dataset, database_id=database_id)
            final_sql = sql
            final_executable = (orig_check.get("status") == "success")
            current_exec = orig_check
            termination_reason = "Query remained non-executable after repair attempts; reverted to original query per MapleDoctor termination protocol"
            trace.append(f"MapleDoctor TERMINATION: {termination_reason}")

        was_repaired = (final_sql != sql)

        return MapleDoctorResult(
            original_sql=sql,
            final_sql=final_sql,
            was_repaired=was_repaired,
            error_detected=True,
            initial_detection=initial_detection,
            iterations=len(repair_history),
            repair_history=repair_history,
            is_executable=final_executable,
            final_execution_data=current_exec,
            trace=trace,
            termination_reason=termination_reason
        )
