import re
from typing import Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule
from src.mapledoctor.ast_utils import add_is_not_null_to_where

class AscendingSortWithNullRule(MapleRule):
    """
    Rule 8: ASCENDING SORT WITH NULL
    Ascending sort or MIN() on a nullable column causes NULL to sort first.
    Example from paper:
        SELECT MIN(price) FROM products
        ->
        SELECT MIN(price) FROM products WHERE price IS NOT NULL
    Preserves all existing WHERE conditions and query structure.
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.ASCENDING_SORT_WITH_NULL

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule8_AscendingSortWithNull"

    def can_repair(self, detection: DetectionResult) -> bool:
        return detection.category == ErrorCategory.ASCENDING_SORT_WITH_NULL

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        col_name = detection.location.column or detection.evidence.get("column")
        tbl_name = detection.location.table or detection.evidence.get("table")

        if not col_name:
            return None, None, 0.0

        repaired = add_is_not_null_to_where(sql, col_name, tbl_name)
        if repaired != sql:
            return (
                repaired,
                f"{self.name}(Added {col_name} IS NOT NULL to WHERE)",
                0.94
            )

        return None, None, 0.0
