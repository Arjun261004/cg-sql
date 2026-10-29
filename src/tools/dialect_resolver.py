from typing import Dict, Any, Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase

class DialectResolver:
    """
    Internal Dialect Resolver for SQLGenerationAgent and ValidationExecutionAgent.
    Resolves the dialect and dialect rules deterministically from KB configuration.
    Supports SQLite, DuckDB, Snowflake, BigQuery, PostgreSQL, MySQL.
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb

    def resolve_dialect(
        self,
        dataset: str,
        database_id: str,
        requested_dialect: Optional[str] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Resolves target dialect and dialect rules from KB."""
        dialect = requested_dialect or "SQLite"
        rules_dict = None

        if self.kb:
            db_meta = self.kb.get_database(dataset, database_id)
            if db_meta and db_meta.get("dialect"):
                dialect = db_meta["dialect"]
            elif not requested_dialect:
                dialect = "SQLite"

            rules = self.kb.get_dialect_rules(dialect)
            if rules:
                rules_dict = rules.dict() if hasattr(rules, "dict") else rules

        return dialect, rules_dict

    def format_guidelines(self, dialect: str, dialect_rules: Optional[Dict[str, Any]]) -> str:
        """Formats prompt instructions based on dialect rules."""
        if not dialect_rules:
            return f"Generate standard {dialect} SQL syntax."

        guidelines = [f"Dialect Rules for {dialect}:"]
        if dialect_rules.get("supported_functions"):
            guidelines.append(f"- Supported functions: {', '.join(dialect_rules['supported_functions'][:10])}")
        if dialect_rules.get("date_syntax"):
            guidelines.append(f"- Date syntax: {dialect_rules['date_syntax']}")
        if dialect_rules.get("known_restrictions"):
            guidelines.append(f"- Restrictions: {', '.join(dialect_rules['known_restrictions'])}")

        return "\n".join(guidelines)

