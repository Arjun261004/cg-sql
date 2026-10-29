from typing import Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule

class SuspiciousSymptomsRule(MapleRule):
    """
    Suspicious execution symptoms handler:
    - EMPTY_RESULT
    - SINGLE_NULL_RESULT
    
    Paper Logic:
    Semantic errors are harder to detect statically; execution symptoms are used
    as proxies. Since these require semantic reasoning over the question and data,
    MapleDoctor uses targeted LLM-assisted repair.
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.EMPTY_RESULT

    @property
    def name(self) -> str:
        return "MapleDoctor_SuspiciousSymptoms"

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
        return None, "Suspicious symptoms require LLM-assisted semantic diagnosis", 0.0
