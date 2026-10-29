import re
from typing import Optional, Tuple, List
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule
from src.mapledoctor.ast_utils import parse_sql, extract_tables_and_aliases

class TableColumnMismatchRule(MapleRule):
    """
    Rule 2: TABLE-COLUMN MISMATCH
    The SQL references a column in table A, but that column belongs to table B.
    
    Paper Logic:
    IF exactly one table contains the column:
        Replace the incorrect table reference with that table.
    IF multiple tables contain the column:
        Do NOT make an arbitrary choice. Invoke LLM fallback.
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.TABLE_COLUMN_MISMATCH

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule2_TableColumnMismatch"

    def can_repair(self, detection: DetectionResult) -> bool:
        if detection.category != ErrorCategory.TABLE_COLUMN_MISMATCH:
            return False
        # Must have exactly one matching table for deterministic repair
        matching_tables = detection.evidence.get("matching_tables", [])
        return len(matching_tables) == 1

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        matching_tables: List[str] = detection.evidence.get("matching_tables", [])
        wrong_table = detection.evidence.get("wrong_table") or detection.location.table
        col_name = detection.evidence.get("column") or detection.location.column

        if len(matching_tables) == 1 and wrong_table and col_name:
            correct_table = matching_tables[0]
            # Pattern: wrong_table.col_name -> correct_table.col_name
            pattern = re.compile(rf'\b{re.escape(wrong_table)}\.{re.escape(col_name)}\b', re.IGNORECASE)
            repaired = pattern.sub(f"{correct_table}.{col_name}", sql)
            if repaired != sql:
                return (
                    repaired,
                    f"{self.name}({wrong_table}.{col_name} -> {correct_table}.{col_name})",
                    0.96
                )

        # Ambiguous (multiple candidate tables) -> Do not make arbitrary choice
        return None, "Multiple candidate tables contain this column; requires LLM fallback", 0.0
