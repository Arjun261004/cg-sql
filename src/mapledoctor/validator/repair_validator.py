from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.ast_utils import parse_sql, extract_tables_and_aliases, extract_columns
from sqlglot import exp

class ValidationOutcome(BaseModel):
    is_valid: bool
    is_executable: bool
    previous_error_resolved: bool
    remaining_error: Optional[str] = None
    execution_dict: Dict[str, Any] = Field(default_factory=dict)
    safety_violations: List[str] = Field(default_factory=list)

class RepairValidator:
    """
    Validates repaired SQL against paper-identified mis-repair failure modes
    and re-executes against the target database engine to verify true executability.
    """

    def __init__(self, executor: Optional[Any] = None, kb: Optional[KnowledgeBase] = None):
        if executor is None:
            from src.tools.database_executor import DatabaseExecutor
            self.executor = DatabaseExecutor()
        else:
            self.executor = executor
        self.kb = kb

    def validate_repair(
        self,
        original_sql: str,
        repaired_sql: str,
        original_detection: Optional[DetectionResult],
        dialect: str = "SQLite",
        db_path: str = "",
        dataset: str = "spider",
        database_id: str = "default"
    ) -> ValidationOutcome:
        safety_violations = []

        if not repaired_sql or not repaired_sql.strip():
            return ValidationOutcome(
                is_valid=False,
                is_executable=False,
                previous_error_resolved=False,
                remaining_error="Repaired SQL is empty",
                safety_violations=["Empty SQL returned"]
            )

        # 1. Parse check
        orig_tree = parse_sql(original_sql, dialect=dialect)
        rep_tree = parse_sql(repaired_sql, dialect=dialect)

        if not rep_tree:
            return ValidationOutcome(
                is_valid=False,
                is_executable=False,
                previous_error_resolved=False,
                remaining_error="Repaired SQL failed syntax parsing",
                safety_violations=["Parse error in repaired SQL"]
            )

        # 2. Mis-repair failure mode checks (from paper)
        # Check 1: Extremum rewrite (MAX/MIN -> ORDER BY + LIMIT 1)
        if orig_tree and original_detection and original_detection.category != ErrorCategory.AGGREGATION_COMPARISON_MISUSE:
            orig_has_min_max = any(isinstance(f, (exp.Min, exp.Max)) for f in orig_tree.find_all(exp.Min, exp.Max))
            rep_has_min_max = any(isinstance(f, (exp.Min, exp.Max)) for f in rep_tree.find_all(exp.Min, exp.Max))
            rep_has_limit = bool(rep_tree.find(exp.Limit))
            if orig_has_min_max and not rep_has_min_max and rep_has_limit:
                safety_violations.append("Extremum rewrite detected: converted MAX/MIN into ORDER BY + LIMIT 1")

        # Check 2: Schema hallucination in repair
        if self.kb:
            schema = self.kb.get_schema(dataset, database_id)
            if schema:
                known_tables = {t.lower() for t in schema.tables.keys()}
                rep_tables = extract_tables_and_aliases(rep_tree)
                for t in rep_tables.keys():
                    if t.lower() not in known_tables and t.upper() not in ["DUAL", "SELECT"]:
                        safety_violations.append(f"Schema hallucination in repair: non-existent table '{t}'")

        # Check 3: Projection drop (accidentally removing requested output columns)
        if orig_tree and rep_tree:
            orig_selects = orig_tree.expressions if hasattr(orig_tree, "expressions") else []
            rep_selects = rep_tree.expressions if hasattr(rep_tree, "expressions") else []
            if len(orig_selects) > 1 and len(rep_selects) < len(orig_selects):
                safety_violations.append(f"Projection drop: original had {len(orig_selects)} columns, repaired has {len(rep_selects)}")

        # 3. Dynamic Re-execution Check
        exec_dict = self.executor.execute(
            sql=repaired_sql,
            dialect=dialect,
            db_path=db_path,
            dataset=dataset,
            database_id=database_id
        )

        is_executable = (exec_dict.get("status") == "success")
        exec_error = exec_dict.get("error")

        # Previous error resolved check
        prev_resolved = True
        if original_detection and original_detection.raw_error and exec_error:
            if original_detection.raw_error.lower() in exec_error.lower():
                prev_resolved = False

        if not is_executable:
            prev_resolved = False

        is_valid = is_executable and len(safety_violations) == 0 and prev_resolved

        return ValidationOutcome(
            is_valid=is_valid,
            is_executable=is_executable,
            previous_error_resolved=prev_resolved,
            remaining_error=exec_error,
            execution_dict=exec_dict,
            safety_violations=safety_violations
        )
