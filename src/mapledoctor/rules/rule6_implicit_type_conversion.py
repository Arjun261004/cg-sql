import re
from typing import Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule
from src.mapledoctor.ast_utils import parse_sql, extract_division_nodes, has_float_cast, is_integer_operand, to_sql
from sqlglot import exp

class ImplicitTypeConversionRule(MapleRule):
    """
    Rule 6: IMPLICIT TYPE CONVERSION
    Division between integer operands without explicit float cast causes integer truncation.
    Example from paper:
        COUNT(*) / 12 -> CAST(COUNT(*) AS REAL) / 12
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.IMPLICIT_TYPE_CONVERSION

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule6_ImplicitTypeConversion"

    def can_repair(self, detection: DetectionResult) -> bool:
        return detection.category == ErrorCategory.IMPLICIT_TYPE_CONVERSION

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        tree = parse_sql(sql, dialect=dialect)
        target_cast_type = "REAL" if dialect == "SQLite" else "FLOAT"

        if tree:
            div_nodes = extract_division_nodes(tree)
            modified = False
            for div in div_nodes:
                left = div.this
                right = div.expression
                if not has_float_cast(left) and not has_float_cast(right):
                    # Wrap left operand in CAST(left AS REAL)
                    cast_expr = exp.Cast(this=left.copy(), to=exp.DataType.build(target_cast_type))
                    div.set("this", cast_expr)
                    modified = True

            if modified:
                repaired = to_sql(tree, dialect=dialect)
                return (
                    repaired,
                    f"{self.name}(Wrapped numerator in CAST(... AS {target_cast_type}))",
                    0.96
                )

        # Fallback regex pattern for division like COUNT(*) / 12
        count_div_match = re.search(r'(COUNT\s*\([^)]*\))\s*/\s*([0-9]+|[a-zA-Z0-9_]+)', sql, re.IGNORECASE)
        if count_div_match:
            numerator = count_div_match.group(1)
            denominator = count_div_match.group(2)
            repaired = sql.replace(
                count_div_match.group(0),
                f"CAST({numerator} AS {target_cast_type}) / {denominator}"
            )
            return (
                repaired,
                f"{self.name}(Regex: CAST({numerator} AS {target_cast_type}) / {denominator})",
                0.95
            )

        return None, None, 0.0
