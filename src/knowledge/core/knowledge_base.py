from typing import List, Dict, Optional, Any
from src.knowledge.core.models import (
    DatabaseSchema, TableSchema, ColumnSchema, Relationship,
    ColumnStatistics, DialectRules, SQLRule, ErrorRule, BusinessDefinition
)
from src.knowledge.core.repository import KnowledgeRepository
from src.knowledge.core.graph import RelationshipGraph
from src.knowledge.core.schema_search import SchemaSearch

class KnowledgeBase:
    """
    Deterministic Knowledge Layer for CG-SQL.
    Provides a shared source of grounded facts. No LLM calls happen here.
    """
    def __init__(self, repo: KnowledgeRepository = None):
        self.repo = repo or KnowledgeRepository()
        self._graph_cache: Dict[str, RelationshipGraph] = {}

    def get_database(self, dataset: str, database_id: str) -> Optional[Dict]:
        schema = self.get_schema(dataset, database_id)
        if schema:
            return {
                "dataset": dataset,
                "database_id": database_id,
                # Additional metadata could be stored, but we extract basic from schema if needed
                "tables_count": len(schema.tables)
            }
        return None

    def get_schema(self, dataset: str, database_id: str) -> Optional[DatabaseSchema]:
        schema = self.repo.get_schema(dataset, database_id)
        if not schema and dataset == "spider":
            try:
                from src.knowledge.ingestion.spider_ingestor import SpiderIngestor
                ingestor = SpiderIngestor()
                if ingestor.ingest_single(database_id):
                    # Ingestion succeeded, try getting it again
                    schema = self.repo.get_schema(dataset, database_id)
            except Exception as e:
                print(f"Lazy ingestion failed for {database_id}: {e}")
        return schema

    def get_table(self, dataset: str, database_id: str, table_name: str) -> Optional[TableSchema]:
        schema = self.get_schema(dataset, database_id)
        if schema and table_name in schema.tables:
            return schema.tables[table_name]
        return None

    def get_columns(self, dataset: str, database_id: str, table_name: str) -> List[ColumnSchema]:
        table = self.get_table(dataset, database_id, table_name)
        return list(table.columns.values()) if table else []

    def get_primary_keys(self, dataset: str, database_id: str, table_name: str) -> List[str]:
        table = self.get_table(dataset, database_id, table_name)
        return table.primary_keys if table else []

    def get_foreign_keys(self, dataset: str, database_id: str, table_name: str) -> List[Dict[str, str]]:
        table = self.get_table(dataset, database_id, table_name)
        return table.foreign_keys if table else []

    def get_relationships(self, dataset: str, database_id: str) -> List[Relationship]:
        return self.repo.get_relationships(dataset, database_id)

    def _get_graph(self, dataset: str, database_id: str) -> RelationshipGraph:
        cache_key = f"{dataset}_{database_id}"
        if cache_key not in self._graph_cache:
            rels = self.get_relationships(dataset, database_id)
            self._graph_cache[cache_key] = RelationshipGraph(rels)
        return self._graph_cache[cache_key]

    def find_join_paths(self, dataset: str, database_id: str, table_a: str, table_b: str) -> List[List[Relationship]]:
        graph = self._get_graph(dataset, database_id)
        return graph.find_join_paths(table_a, table_b)

    def get_dialect_rules(self, dialect: str) -> Optional[DialectRules]:
        return self.repo.get_dialect_rules(dialect)

    def get_column_statistics(self, dataset: str, database_id: str, table_name: str, column_name: str) -> Optional[ColumnStatistics]:
        stats = self.repo.get_statistics(dataset, database_id)
        if table_name in stats and column_name in stats[table_name]:
            return stats[table_name][column_name]
        return None

    def search_schema(self, dataset: str, database_id: str, query: str) -> Dict[str, Any]:
        schema = self.get_schema(dataset, database_id)
        if not schema:
            return {"tables": [], "columns": []}
        searcher = SchemaSearch(schema)
        return searcher.search(query)

    def get_business_definition(self, term: str) -> Optional[BusinessDefinition]:
        defs = self.repo.get_business_definitions()
        term_lower = term.lower()
        for d in defs:
            if d.term.lower() == term_lower:
                return d
        return None

    def get_error_rule(self, error_text: str) -> Optional[ErrorRule]:
        rules = self.repo.get_error_rules()
        error_lower = error_text.lower()
        for rule in rules:
            if rule.pattern.lower() in error_lower:
                return rule
        return None

    def get_sql_rules(self) -> List[SQLRule]:
        return self.repo.get_sql_rules()
