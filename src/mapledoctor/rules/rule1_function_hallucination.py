import re
from typing import Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule

class FunctionHallucinationRule(MapleRule):
    """
    Rule 1: FUNCTION HALLUCINATION
    Replaces unsupported or hallucinated function calls with predefined,
    dialect-supported equivalents for the target DBMS.
    Examples from paper:
        DIVIDE(a, b) -> a / b
        YEAR(x) -> STRFTIME('%Y', x)
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.FUNCTION_HALLUCINATION

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule1_FunctionHallucination"

    def can_repair(self, detection: DetectionResult) -> bool:
        return detection.category == ErrorCategory.FUNCTION_HALLUCINATION

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        repaired = sql
        fn_name = (detection.location.function or detection.evidence.get("function") or "").upper()

        if dialect == "SQLite":
            # 1. DIVIDE(a, b) -> (a / b)
            if fn_name == "DIVIDE" or "DIVIDE(" in repaired.upper():
                repaired = re.sub(
                    r'\bDIVIDE\s*\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)',
                    r'(\1 / \2)',
                    repaired,
                    flags=re.IGNORECASE
                )
                if repaired != sql:
                    return repaired, f"{self.name}(DIVIDE -> /)", 0.98

            # 2. YEAR(x) -> strftime('%Y', x)
            if fn_name == "YEAR" or "YEAR(" in repaired.upper():
                repaired = re.sub(
                    r'\bYEAR\s*\(\s*([^)]+?)\s*\)',
                    r"strftime('%Y', \1)",
                    repaired,
                    flags=re.IGNORECASE
                )
                if repaired != sql:
                    return repaired, f"{self.name}(YEAR -> strftime)", 0.98

            # 3. MONTH(x) -> strftime('%m', x)
            if fn_name == "MONTH" or "MONTH(" in repaired.upper():
                repaired = re.sub(
                    r'\bMONTH\s*\(\s*([^)]+?)\s*\)',
                    r"strftime('%m', \1)",
                    repaired,
                    flags=re.IGNORECASE
                )
                if repaired != sql:
                    return repaired, f"{self.name}(MONTH -> strftime)", 0.98

            # 4. DAY(x) -> strftime('%d', x)
            if fn_name == "DAY" or "DAY(" in repaired.upper():
                repaired = re.sub(
                    r'\bDAY\s*\(\s*([^)]+?)\s*\)',
                    r"strftime('%d', \1)",
                    repaired,
                    flags=re.IGNORECASE
                )
                if repaired != sql:
                    return repaired, f"{self.name}(DAY -> strftime)", 0.98

            # 5. CONCAT(a, b) -> (a || b)
            if fn_name == "CONCAT" or "CONCAT(" in repaired.upper():
                repaired = re.sub(
                    r'\bCONCAT\s*\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)',
                    r'(\1 || \2)',
                    repaired,
                    flags=re.IGNORECASE
                )
                if repaired != sql:
                    return repaired, f"{self.name}(CONCAT -> ||)", 0.98

            # 6. DATE_TRUNC('year', x) or DATE_TRUNC(x, 'year') -> strftime('%Y', x)
            if fn_name == "DATE_TRUNC" or "DATE_TRUNC(" in repaired.upper():
                # Form: DATE_TRUNC('year', col)
                dt_match = re.search(r'DATE_TRUNC\s*\(\s*[\'"]?year[\'"]?\s*,\s*([a-zA-Z0-9_.]+)\s*\)', repaired, re.IGNORECASE)
                if dt_match:
                    col_ref = dt_match.group(1)
                    repaired = re.sub(
                        r'DATE_TRUNC\s*\(\s*[\'"]?year[\'"]?\s*,\s*[a-zA-Z0-9_.]+\s*\)',
                        f"strftime('%Y', {col_ref})",
                        repaired,
                        flags=re.IGNORECASE
                    )
                    return repaired, f"{self.name}(DATE_TRUNC -> strftime('%Y', col))", 0.98

                # Form: DATE_TRUNC('month', col)
                dt_match_m = re.search(r'DATE_TRUNC\s*\(\s*[\'"]?month[\'"]?\s*,\s*([a-zA-Z0-9_.]+)\s*\)', repaired, re.IGNORECASE)
                if dt_match_m:
                    col_ref = dt_match_m.group(1)
                    repaired = re.sub(
                        r'DATE_TRUNC\s*\(\s*[\'"]?month[\'"]?\s*,\s*[a-zA-Z0-9_.]+\s*\)',
                        f"strftime('%Y-%m', {col_ref})",
                        repaired,
                        flags=re.IGNORECASE
                    )
                    return repaired, f"{self.name}(DATE_TRUNC -> strftime('%Y-%m', col))", 0.98

            # 7. NOW() -> CURRENT_TIMESTAMP
            if fn_name == "NOW" or "NOW()" in repaired.upper():
                repaired = re.sub(r'\bNOW\s*\(\s*\)', 'CURRENT_TIMESTAMP', repaired, flags=re.IGNORECASE)
                if repaired != sql:
                    return repaired, f"{self.name}(NOW() -> CURRENT_TIMESTAMP)", 0.98

        elif dialect == "DuckDB":
            if fn_name == "DIVIDE":
                repaired = re.sub(
                    r'\bDIVIDE\s*\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)',
                    r'(\1 / \2)',
                    repaired,
                    flags=re.IGNORECASE
                )
                if repaired != sql:
                    return repaired, f"{self.name}(DIVIDE -> /)", 0.98

            if fn_name == "YEAR":
                repaired = re.sub(r'\bYEAR\s*\(\s*([^)]+?)\s*\)', r'EXTRACT(YEAR FROM \1)', repaired, flags=re.IGNORECASE)
                if repaired != sql:
                    return repaired, f"{self.name}(YEAR -> EXTRACT)", 0.98

        if repaired != sql:
            return repaired, f"{self.name}({fn_name})", 0.95

        return None, None, 0.0
