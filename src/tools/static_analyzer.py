import re
from typing import Dict, List, Any, Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.models.state import SchemaLinkingResult

class StaticValidator:
    """
    Internal Static Validator for ValidationExecutionAgent.
    Validates SQL queries statically prior to execution:
    checks that referenced tables and columns exist in the database schema.
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb

    def validate_sql(
        self,
        sql: str,
        dataset: str,
        database_id: str,
        schema_linking: Optional[SchemaLinkingResult] = None
    ) -> Dict[str, Any]:
        """Statically verifies table and column existence against the Knowledge Base."""
        errors: List[str] = []
        warnings: List[str] = []

        if not sql or not sql.strip():
            return {"valid": False, "errors": ["Empty SQL"], "warnings": []}

        clean_sql = sql.strip()

        # Check table references
        if self.kb:
            schema = self.kb.get_schema(dataset, database_id)
            if schema and schema.tables:
                known_tables = {t.lower(): t for t in schema.tables.keys()}
                
                # Regex match FROM <table> and JOIN <table>
                table_refs = re.findall(r'(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)', clean_sql, re.IGNORECASE)
                for t in table_refs:
                    if t.lower() not in known_tables and t.upper() not in ["DUAL", "SELECT"]:
                        errors.append(f"Referenced table '{t}' does not exist in schema for database '{database_id}'")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

class ErrorClassifier:
    """
    Internal Error Classifier for RepairAgent.
    Extracts symptoms and classifies errors into standard categories:
    - FUNCTION_HALLUCINATION
    - TABLE_COLUMN_MISMATCH
    - UNUSED_ALIAS
    - SCHEMA_HALLUCINATION
    - MISSING_JOIN
    - IMPLICIT_TYPE_CONVERSION
    - EQUALS_INSTEAD_OF_IN
    - ASCENDING_SORT_WITH_NULL
    - COMPARING_UNRELATED_COLUMNS
    - VIOLATING_VALUE_SPECIFICATION
    - AGGREGATION_COMPARISON_MISUSE
    - NO_SUCH_TABLE / NO_SUCH_COLUMN
    - SYNTAX_ERROR
    - EMPTY_RESULT / SINGLE_NULL_RESULT
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb

    def classify_error(self, error_text: str, sql: str = "") -> Dict[str, Any]:
        """Categorizes the error and extracts symptom parameters."""
        if not error_text and not sql:
            return {"category": "UNKNOWN", "symptom": "", "details": {}}

        err_lower = (error_text or "").lower()

        # Try MapleDoctor UniversalDetector first if available
        try:
            from src.mapledoctor.detector.detector import UniversalDetector
            detector = UniversalDetector(kb=self.kb)
            detection = detector.detect(
                sql=sql,
                error_text=error_text,
                kb=self.kb
            )
            if detection:
                return {
                    "category": detection.category.value,
                    "symptom": detection.description,
                    "details": {
                        "category": detection.category.value,
                        "description": detection.description,
                        "location": detection.location.dict(),
                        "evidence": detection.evidence,
                        "raw_error": error_text,
                        "rule_applicable": detection.is_rule_applicable
                    }
                }
        except Exception:
            pass
        
        # 1. Check deterministic error rules from KB
        if self.kb and error_text:
            rule = self.kb.get_error_rule(error_text)
            if rule:
                return {
                    "category": rule.error_type,
                    "symptom": rule.pattern,
                    "strategies": rule.repair_strategies,
                    "details": {"rule": rule.model_dump() if hasattr(rule, "model_dump") else (rule.dict() if hasattr(rule, "dict") else rule), "raw_error": error_text}
                }

        # 2. Heuristic and pattern-based classification
        # NO_SUCH_COLUMN
        col_match = re.search(r'no such column:?\s*([a-zA-Z0-9_.]+)', error_text or "", re.IGNORECASE)
        if not col_match:
            col_match = re.search(r'column\s+["\']?([a-zA-Z0-9_.]+)["\']?\s+does not exist', error_text or "", re.IGNORECASE)
        if col_match:
            col_name = col_match.group(1).split('.')[-1]
            return {
                "category": "NO_SUCH_COLUMN",
                "symptom": col_name,
                "details": {"column": col_name, "raw_error": error_text}
            }

        # NO_SUCH_TABLE
        tbl_match = re.search(r'no such table:?\s*([a-zA-Z0-9_]+)', error_text or "", re.IGNORECASE)
        if not tbl_match:
            tbl_match = re.search(r'table\s+["\']?([a-zA-Z0-9_]+)["\']?\s+does not exist', error_text or "", re.IGNORECASE)
        if tbl_match:
            tbl_name = tbl_match.group(1)
            return {
                "category": "NO_SUCH_TABLE",
                "symptom": tbl_name,
                "details": {"table": tbl_name, "raw_error": error_text}
            }

        # DIALECT_ERROR / INVALID_FUNCTION
        if "date_trunc" in err_lower or "strftime" in err_lower or "extract(" in err_lower:
            return {
                "category": "DIALECT_ERROR",
                "symptom": "Date function dialect incompatibility",
                "details": {"raw_error": error_text}
            }
        if "no such function" in err_lower or "unknown function" in err_lower:
            fn_match = re.search(r'function:?\s*([a-zA-Z0-9_]+)', error_text or "", re.IGNORECASE)
            fn_name = fn_match.group(1) if fn_match else "unknown"
            return {
                "category": "INVALID_FUNCTION",
                "symptom": fn_name,
                "details": {"function": fn_name, "raw_error": error_text}
            }

        # SYNTAX_ERROR
        if "syntax error" in err_lower or "near" in err_lower or "parse error" in err_lower:
            return {
                "category": "SYNTAX_ERROR",
                "symptom": "SQL syntax error",
                "details": {"raw_error": error_text}
            }

        # INVALID_JOIN
        if "ambiguous column" in err_lower or "ambiguous" in err_lower:
            return {
                "category": "INVALID_ALIAS",
                "symptom": "Ambiguous column reference in join",
                "details": {"raw_error": error_text}
            }

        # EMPTY_RESULT / DUPLICATE_ROWS
        if "empty result" in err_lower or "0 rows" in err_lower:
            return {
                "category": "EMPTY_RESULT",
                "symptom": "Query executed but returned 0 rows unexpectedly",
                "details": {"raw_error": error_text}
            }

        return {
            "category": "SYNTAX_ERROR",
            "symptom": (error_text or "")[:60],
            "details": {"raw_error": error_text}
        }
