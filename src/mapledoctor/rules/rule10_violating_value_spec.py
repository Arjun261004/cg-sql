from typing import Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule

class ViolatingValueSpecificationRule(MapleRule):
    """
    Rule 10: VIOLATING VALUE SPECIFICATION
    The query uses a value that violates known column value specifications
    (e.g. enum case mismatch 'legal' vs 'Legal').
    
    Paper Logic:
    This is an LLM-assisted repair in MapleDoctor.
    The rule delegates to the LLM repairer, providing the target value,
    valid specification values, and targeted repair instructions.
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.VIOLATING_VALUE_SPECIFICATION

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule10_ViolatingValueSpecification"

    def can_repair(self, detection: DetectionResult) -> bool:
        # LLM-assisted repair per paper specification
        return False

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        # Paper explicitly defines Rule 10 as LLM-assisted repair
        return None, "Rule 10 requires LLM-assisted semantic value mapping", 0.0
