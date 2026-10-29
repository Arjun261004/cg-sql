from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult
from src.mapledoctor.probes import DatabaseProber

class BaseDetector(ABC):
    """Abstract base class for MapleDoctor error detectors."""

    @abstractmethod
    def detect(
        self,
        sql: str,
        error_text: Optional[str] = None,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        db_path: str = "",
        kb: Optional[KnowledgeBase] = None,
        prober: Optional[DatabaseProber] = None,
        execution_dict: Optional[Dict[str, Any]] = None,
        question: str = ""
    ) -> Optional[DetectionResult]:
        pass
