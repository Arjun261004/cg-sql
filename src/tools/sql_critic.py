import re
from typing import Dict, List, Any, Optional
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.models.state import SchemaLinkingResult

class SQLCritic:
    """
    Internal SQL critique component for ValidationExecutionAgent.
    Performs deterministic and heuristic adversarial critique of generated SQL candidates.
    Checks SQL rules, dialect rules, Cartesian joins, and ambiguous constructs.
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb

    def critique(
        self,
        sql: str,
        dialect: str = "SQLite",
        dialect_rules: Optional[Dict[str, Any]] = None,
        schema_linking: Optional[SchemaLinkingResult] = None
    ) -> Dict[str, Any]:
        """Runs adversarial critique on a SQL candidate."""
        issues: List[str] = []
        warnings: List[str] = []

        if not sql or not sql.strip():
            return {
                "passed": False,
                "issues": ["Empty SQL query string provided"],
                "warnings": [],
                "confidence": 0.0
            }

        clean_sql = sql.strip()

        # 1. Check deterministic SQL rules from Knowledge Base
        if self.kb:
            sql_rules = self.kb.get_sql_rules()
            for rule in sql_rules:
                if re.search(rule.pattern, clean_sql, re.IGNORECASE):
                    issues.append(f"SQL Rule Violation: {rule.description}")

        # 2. Check dialect rules and known restrictions
        if dialect_rules:
            restrictions = dialect_rules.get("known_restrictions", [])
            for r in restrictions:
                # E.g. SQLite does not have EXTRACT(
                if "EXTRACT" in r.upper() and re.search(r'\bEXTRACT\s*\(', clean_sql, re.IGNORECASE):
                    issues.append(f"Dialect Restriction Violation ({dialect}): {r}")
                if "DATE_TRUNC" in r.upper() and re.search(r'\bDATE_TRUNC\s*\(', clean_sql, re.IGNORECASE):
                    issues.append(f"Dialect Restriction Violation ({dialect}): {r}")

        # 3. Structural checks: Cartesian join detection (comma join without WHERE)
        if re.search(r'FROM\s+[a-zA-Z0-9_]+\s*,\s*[a-zA-Z0-9_]+', clean_sql, re.IGNORECASE):
            if "WHERE" not in clean_sql.upper():
                warnings.append("Cartesian product warning: multiple tables joined with comma syntax without WHERE clause")

        # 4. Multi-table join duplicate row check
        join_count = len(re.findall(r'\bJOIN\b', clean_sql, re.IGNORECASE))
        if join_count > 1 and "DISTINCT" not in clean_sql.upper() and "GROUP BY" not in clean_sql.upper():
            warnings.append("Multi-table join without DISTINCT or GROUP BY carries high duplicate-row risk")

        passed = len(issues) == 0
        confidence = 0.95 if passed and not warnings else (0.75 if passed else 0.2)

        return {
            "passed": passed,
            "issues": issues,
            "warnings": warnings,
            "confidence": confidence
        }

