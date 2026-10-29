import re
from typing import Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule

class SchemaHallucinationRule(MapleRule):
    """
    Rule 4: SCHEMA HALLUCINATION
    The SQL references a non-existent column or table.
    
    Paper Logic:
    Attempt to find a similar column/table name using EDIT DISTANCE.
    Example: customer_nmae -> customer_name
    IF a sufficiently suitable candidate exists:
        use the candidate.
    IF no suitable candidate exists:
        invoke LLM fallback. Do not fabricate schema elements.
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.SCHEMA_HALLUCINATION

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule4_SchemaHallucination"

    def can_repair(self, detection: DetectionResult) -> bool:
        if detection.category != ErrorCategory.SCHEMA_HALLUCINATION:
            return False
        return bool(detection.is_rule_applicable and detection.evidence.get("best_match"))

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        hallucinated_col = detection.evidence.get("hallucinated_column")
        hallucinated_tbl = detection.evidence.get("hallucinated_table")
        best_match = detection.evidence.get("best_match")

        if not best_match:
            return None, "No confident edit-distance candidate found; requires LLM fallback", 0.0

        if hallucinated_col:
            pattern = re.compile(rf'\b{re.escape(hallucinated_col)}\b', re.IGNORECASE)
            repaired = pattern.sub(best_match, sql)
            if repaired != sql:
                return (
                    repaired,
                    f"{self.name}(Column: {hallucinated_col} -> {best_match})",
                    0.94
                )

        if hallucinated_tbl:
            pattern = re.compile(rf'\b{re.escape(hallucinated_tbl)}\b', re.IGNORECASE)
            repaired = pattern.sub(best_match, sql)
            if repaired != sql:
                return (
                    repaired,
                    f"{self.name}(Table: {hallucinated_tbl} -> {best_match})",
                    0.94
                )

        return None, None, 0.0
