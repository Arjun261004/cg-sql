from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory

class MapleRule(ABC):
    """Abstract base class for deterministic MapleDoctor repair rules."""

    @property
    @abstractmethod
    def category(self) -> ErrorCategory:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def can_repair(self, detection: DetectionResult) -> bool:
        """Determines if this rule can deterministically repair the detected error."""
        pass

    @abstractmethod
    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Applies deterministic repair.
        Returns:
            Tuple[repaired_sql, rule_name, confidence]
            If ambiguous or requiring LLM fallback, returns (None, reason, 0.0).
        """
        pass
