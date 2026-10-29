from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseDatasetIngestor(ABC):
    """
    Abstract base class for dataset ingestors.
    """
    def __init__(self, dataset_name: str, repo_path: str = "src/knowledge/stores"):
        self.dataset_name = dataset_name
        self.repo_path = repo_path
        from src.knowledge.core.repository import KnowledgeRepository
        self.repo = KnowledgeRepository(repo_path)

    @abstractmethod
    def discover(self) -> int:
        """Discover databases to ingest. Returns count."""
        pass

    @abstractmethod
    def ingest(self, limit: int = None) -> None:
        """Ingest discovered databases."""
        pass

    @abstractmethod
    def validate(self) -> Dict[str, Any]:
        """Validate the ingested knowledge for consistency."""
        pass

    @abstractmethod
    def report(self) -> Dict[str, Any]:
        """Return a summary report of ingestion."""
        pass
