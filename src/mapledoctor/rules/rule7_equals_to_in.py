import re
from typing import Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule
from src.mapledoctor.ast_utils import parse_sql, extract_subquery_equalities, to_sql
from sqlglot import exp

class EqualsInsteadOfInRule(MapleRule):
    """
    Rule 7: USING '=' INSTEAD OF 'IN'
    The '=' operator is used when the right-hand side subquery represents a set
    of multiple possible values.
    Example from paper:
        column = (SELECT ...) -> column IN (SELECT ...)
    IMPORTANT:
        Do not blindly replace every '=' with 'IN'. Only when RHS represents a set.
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.EQUALS_INSTEAD_OF_IN

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule7_EqualsInsteadOfIn"

    def can_repair(self, detection: DetectionResult) -> bool:
        return detection.category == ErrorCategory.EQUALS_INSTEAD_OF_IN

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        col_name = detection.location.column or detection.evidence.get("column")

        tree = parse_sql(sql, dialect=dialect)
        if tree:
            subq_equalities = extract_subquery_equalities(tree)
            modified = False
            for eq_node, col_node, subq_node in subq_equalities:
                if not col_name or col_node.name.lower() == col_name.lower():
                    # Replace EQ with In
                    in_expr = exp.In(this=col_node.copy(), expressions=[subq_node.copy()])
                    eq_node.replace(in_expr)
                    modified = True

            if modified:
                repaired = to_sql(tree, dialect=dialect)
                return (
                    repaired,
                    f"{self.name}(= (subquery) -> IN (subquery))",
                    0.96
                )

        # Regex fallback for col = (SELECT ...)
        col_pattern = re.escape(col_name) if col_name else r'[a-zA-Z0-9_.]+'
        pattern = re.compile(rf'(\b{col_pattern}\b)\s*=\s*(\(\s*SELECT\b)', re.IGNORECASE)
        if pattern.search(sql):
            repaired = pattern.sub(r'\1 IN \2', sql)
            return (
                repaired,
                f"{self.name}(Regex: = (SELECT ...) -> IN (SELECT ...))",
                0.95
            )

        return None, None, 0.0
