import re
from typing import Dict, Any, Optional, Tuple, List
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.engine import MapleDoctorEngine
from src.mapledoctor.repair.rule_repairer import RuleRepairer
from src.mapledoctor.detector.detector import UniversalDetector
from src.mapledoctor.models import (
    DetectionResult,
    ErrorCategory,
    MapleDoctorResult,
    RepairStrategy
)

class MAPLEDoctorRepairer:
    """
    Internal MAPLEDoctor Rule-First Repair Engine for RepairAgent.
    Applies deterministic, rule-based repair transformations to failed SQL queries
    based on error classification, symptom patterns, AST analysis, and Knowledge Base schema facts.
    Implements all 11 MapleDoctor rules from Shen et al. (FSE 2026).
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None, llm_client: Optional[Any] = None):
        self.kb = kb
        self.engine = MapleDoctorEngine(kb=kb, llm_client=llm_client)
        self.rule_repairer = RuleRepairer(kb=kb)
        self.detector = UniversalDetector(kb=kb, prober=self.engine.prober)

    def attempt_rule_repair(
        self,
        failed_sql: str,
        classification: Dict[str, Any],
        dataset: str,
        database_id: str,
        dialect: str = "SQLite"
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Attempts to fix the failed SQL deterministically using MAPLEDoctor rules.
        Returns:
            Tuple[repaired_sql, rule_applied, confidence]
            If no deterministic rule can be applied, returns (None, None, 0.0).
        """
        category = classification.get("category", "")
        symptom = classification.get("symptom", "")
        details = classification.get("details", {})
        raw_error = details.get("raw_error") or symptom

        # 1. First run the UniversalDetector to see if a formal MapleDoctor detection matches
        detection = self.detector.detect(
            sql=failed_sql,
            error_text=raw_error if raw_error else None,
            dataset=dataset,
            database_id=database_id,
            dialect=dialect
        )

        if detection and detection.is_rule_applicable:
            repaired_sql, rule_name, conf = self.rule_repairer.attempt_repair(
                sql=failed_sql,
                detection=detection,
                dataset=dataset,
                database_id=database_id,
                dialect=dialect
            )
            if repaired_sql and conf >= 0.85:
                return repaired_sql, rule_name, conf

        # 2. Existing backwards-compatible rule checks
        # Rule: NO_SUCH_COLUMN repair
        if category in ["NO_SUCH_COLUMN", "TABLE_COLUMN_MISMATCH", "SCHEMA_HALLUCINATION"]:
            invalid_col = details.get("column") or symptom
            if invalid_col and self.kb:
                search_res = self.kb.search_schema(dataset, database_id, invalid_col)
                if search_res.get("columns"):
                    best_match = search_res["columns"][0]["name"]
                    if best_match.lower() != invalid_col.lower():
                        pattern = re.compile(rf'\b{re.escape(invalid_col)}\b', re.IGNORECASE)
                        repaired = pattern.sub(best_match, failed_sql)
                        if repaired != failed_sql:
                            return (
                                repaired,
                                f"MAPLEDoctor_ColumnReplacement({invalid_col} -> {best_match})",
                                0.95
                            )

        # Rule: NO_SUCH_TABLE repair
        if category in ["NO_SUCH_TABLE", "SCHEMA_HALLUCINATION"]:
            invalid_table = details.get("table") or symptom
            if invalid_table and self.kb:
                search_res = self.kb.search_schema(dataset, database_id, invalid_table)
                if search_res.get("tables"):
                    best_match = search_res["tables"][0]["name"]
                    pattern = re.compile(rf'\b{re.escape(invalid_table)}\b', re.IGNORECASE)
                    repaired = pattern.sub(best_match, failed_sql)
                    if repaired != failed_sql:
                        return (
                            repaired,
                            f"MAPLEDoctor_TableReplacement({invalid_table} -> {best_match})",
                            0.95
                        )

        # Rule: DIALECT_ERROR - Date function mismatch
        if category in ["DIALECT_ERROR", "INVALID_FUNCTION", "FUNCTION_HALLUCINATION"] or "DATE_TRUNC" in failed_sql.upper():
            if dialect == "SQLite":
                dt_match = re.search(r'DATE_TRUNC\s*\(\s*[\'"]?year[\'"]?\s*,\s*([a-zA-Z0-9_.]+)\s*\)', failed_sql, re.IGNORECASE)
                if dt_match:
                    col_ref = dt_match.group(1)
                    repaired = re.sub(
                        r'DATE_TRUNC\s*\(\s*[\'"]?year[\'"]?\s*,\s*[a-zA-Z0-9_.]+\s*\)',
                        f"strftime('%Y', {col_ref})",
                        failed_sql,
                        flags=re.IGNORECASE
                    )
                    return repaired, "MAPLEDoctor_DateTruncToSQLiteStrftimeYear", 0.98

                dt_match_month = re.search(r'DATE_TRUNC\s*\(\s*[\'"]?month[\'"]?\s*,\s*([a-zA-Z0-9_.]+)\s*\)', failed_sql, re.IGNORECASE)
                if dt_match_month:
                    col_ref = dt_match_month.group(1)
                    repaired = re.sub(
                        r'DATE_TRUNC\s*\(\s*[\'"]?month[\'"]?\s*,\s*[a-zA-Z0-9_.]+\s*\)',
                        f"strftime('%Y-%m', {col_ref})",
                        failed_sql,
                        flags=re.IGNORECASE
                    )
                    return repaired, "MAPLEDoctor_DateTruncToSQLiteStrftimeMonth", 0.98

                if "DATE_TRUNC" in failed_sql:
                    repaired = failed_sql.replace("DATE_TRUNC", "strftime('%Y',") + ")"
                    return repaired, "MAPLEDoctor_GenericDateTruncCorrection", 0.85

            elif dialect == "Snowflake":
                if "DATE_TRUNC" in failed_sql:
                    repaired = failed_sql.replace("DATE_TRUNC", "DATE_TRUNC_SNOWFLAKE_MOCK")
                    return repaired, "MAPLEDoctor_SnowflakeSyntaxFix", 0.90

        # Rule: SYNTAX_ERROR - Trailing comma before FROM or WHERE
        if category == "SYNTAX_ERROR":
            cleaned = re.sub(r',\s*FROM\b', ' FROM', failed_sql, flags=re.IGNORECASE)
            cleaned = re.sub(r',\s*WHERE\b', ' WHERE', cleaned, flags=re.IGNORECASE)
            if cleaned != failed_sql:
                return cleaned, "MAPLEDoctor_TrailingCommaRemoval", 0.92

        # No deterministic rule applicable
        return None, None, 0.0

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
        """Runs the full MapleDoctor diagnostic & repair pipeline."""
        return self.engine.diagnose_and_repair(
            sql=sql,
            question=question,
            error_text=error_text,
            dataset=dataset,
            database_id=database_id,
            dialect=dialect,
            db_path=db_path,
            execution_dict=execution_dict,
            max_repairs=max_repairs
        )
