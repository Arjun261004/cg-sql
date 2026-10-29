import re
from typing import Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule

class UnusedAliasRule(MapleRule):
    """
    Rule 3: UNUSED ALIAS
    A table has been assigned an alias, but the query continues to reference
    the original table name instead of the assigned alias.
    Example from paper:
        FROM students AS S SELECT students.name -> SELECT S.name
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.UNUSED_ALIAS

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule3_UnusedAlias"

    def can_repair(self, detection: DetectionResult) -> bool:
        return detection.category == ErrorCategory.UNUSED_ALIAS

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        table_name = detection.evidence.get("table") or detection.location.table
        alias_name = detection.evidence.get("alias")
        col_name = detection.evidence.get("column") or detection.location.column

        if not table_name or not alias_name:
            return None, None, 0.0

        # Replace table_name.col with alias_name.col everywhere in SQL
        if col_name:
            pattern = re.compile(rf'\b{re.escape(table_name)}\.{re.escape(col_name)}\b', re.IGNORECASE)
            repaired = pattern.sub(f"{alias_name}.{col_name}", sql)
        else:
            # Replace table_name.<any_col> with alias_name.<any_col> (excluding FROM table_name AS alias)
            pattern = re.compile(rf'(?<!FROM\s)(?<!JOIN\s)\b{re.escape(table_name)}\.([a-zA-Z0-9_]+)', re.IGNORECASE)
            repaired = pattern.sub(rf"{alias_name}.\1", sql)

        if repaired != sql:
            return (
                repaired,
                f"{self.name}({table_name} -> {alias_name})",
                0.98
            )

        return None, None, 0.0
