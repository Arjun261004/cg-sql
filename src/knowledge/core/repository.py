import json
import os
from typing import Dict, List, Optional, Any
from src.knowledge.core.models import (
    DatabaseSchema, Relationship, ColumnStatistics, DialectRules,
    SQLRule, ErrorRule, BusinessDefinition
)

class KnowledgeRepository:
    """
    Handles reading and writing KB facts from/to JSON stores.
    Provides in-memory caching to avoid repeated disk reads.
    """
    def __init__(self, base_path: str = "src/knowledge/stores"):
        self.base_path = base_path
        self._cache: Dict[str, Any] = {}

    def _get_path(self, category: str, dataset: Optional[str] = None, file_name: str = "") -> str:
        if dataset:
            return os.path.join(self.base_path, category, dataset, file_name)
        return os.path.join(self.base_path, category, file_name)

    def _load_json(self, path: str) -> Optional[Any]:
        if path in self._cache:
            return self._cache[path]
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._cache[path] = data
                return data
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {path}")
            return None

    def _save_json(self, path: str, data: Any):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        self._cache[path] = data

    # Schema
    def get_schema(self, dataset: str, database_id: str) -> Optional[DatabaseSchema]:
        path = self._get_path("schemas", dataset, f"{database_id}.json")
        data = self._load_json(path)
        if data:
            return DatabaseSchema(**data)
        return None

    def save_schema(self, dataset: str, database_id: str, schema: DatabaseSchema):
        path = self._get_path("schemas", dataset, f"{database_id}.json")
        self._save_json(path, schema.dict())

    # Relationships
    def get_relationships(self, dataset: str, database_id: str) -> List[Relationship]:
        path = self._get_path("relationships", dataset, f"{database_id}.json")
        data = self._load_json(path)
        if data:
            return [Relationship(**r) for r in data]
        return []

    def save_relationships(self, dataset: str, database_id: str, relationships: List[Relationship]):
        path = self._get_path("relationships", dataset, f"{database_id}.json")
        self._save_json(path, [r.dict() for r in relationships])

    # Statistics
    def get_statistics(self, dataset: str, database_id: str) -> Dict[str, Dict[str, ColumnStatistics]]:
        path = self._get_path("statistics", dataset, f"{database_id}.json")
        data = self._load_json(path)
        if data:
            # Format: {"table_name": {"column_name": {...}}}
            return {t: {c: ColumnStatistics(**s) for c, s in cols.items()} for t, cols in data.items()}
        return {}

    def save_statistics(self, dataset: str, database_id: str, stats: Dict[str, Dict[str, ColumnStatistics]]):
        path = self._get_path("statistics", dataset, f"{database_id}.json")
        serializable_stats = {t: {c: s.dict() for c, s in cols.items()} for t, cols in stats.items()}
        self._save_json(path, serializable_stats)

    # Dialects
    def get_dialect_rules(self, dialect: str) -> Optional[DialectRules]:
        path = self._get_path("dialects", file_name=f"{dialect.lower()}.json")
        data = self._load_json(path)
        if data:
            return DialectRules(**data)
        return None

    def save_dialect_rules(self, dialect: str, rules: DialectRules):
        path = self._get_path("dialects", file_name=f"{dialect.lower()}.json")
        self._save_json(path, rules.dict())

    # SQL Rules
    def get_sql_rules(self) -> List[SQLRule]:
        rules = []
        rules_dir = os.path.join(self.base_path, "sql_rules")
        if os.path.exists(rules_dir):
            for file_name in os.listdir(rules_dir):
                if file_name.endswith('.json'):
                    data = self._load_json(os.path.join(rules_dir, file_name))
                    if data and isinstance(data, list):
                        rules.extend([SQLRule(**r) for r in data])
        return rules
        
    def save_sql_rules(self, category: str, rules: List[SQLRule]):
        path = self._get_path("sql_rules", file_name=f"{category}.json")
        self._save_json(path, [r.dict() for r in rules])

    # Error Rules
    def get_error_rules(self) -> List[ErrorRule]:
        rules = []
        rules_dir = os.path.join(self.base_path, "error_rules")
        if os.path.exists(rules_dir):
            for file_name in os.listdir(rules_dir):
                if file_name.endswith('.json'):
                    data = self._load_json(os.path.join(rules_dir, file_name))
                    if data and isinstance(data, list):
                        rules.extend([ErrorRule(**r) for r in data])
        return rules
        
    def save_error_rules(self, category: str, rules: List[ErrorRule]):
        path = self._get_path("error_rules", file_name=f"{category}.json")
        self._save_json(path, [r.dict() for r in rules])

    # Business Rules
    def get_business_definitions(self) -> List[BusinessDefinition]:
        defs = []
        rules_dir = os.path.join(self.base_path, "business_rules")
        if os.path.exists(rules_dir):
            for file_name in os.listdir(rules_dir):
                if file_name.endswith('.json'):
                    data = self._load_json(os.path.join(rules_dir, file_name))
                    if data and isinstance(data, list):
                        defs.extend([BusinessDefinition(**d) for d in data])
        return defs
