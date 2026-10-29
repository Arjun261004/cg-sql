import re
from typing import Optional, Tuple, List, Dict, Any
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule

class ComparingUnrelatedColumnsRule(MapleRule):
    """
    Rule 9: COMPARING UNRELATED COLUMNS
    Two columns are compared (especially in JOIN equality) without a valid relationship.
    
    Paper Logic:
    Search for a foreign-key column of the same table that could represent the intended relationship.
    IF exactly one suitable foreign-key candidate exists:
        Replace the incorrect column with that FK column.
    IF multiple candidates exist:
        Invoke the LLM repairer.
    Example from paper:
        cards.id = sets.id -> cards.setCode = sets.code
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.COMPARING_UNRELATED_COLUMNS

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule9_ComparingUnrelatedColumns"

    def can_repair(self, detection: DetectionResult) -> bool:
        if detection.category != ErrorCategory.COMPARING_UNRELATED_COLUMNS:
            return False
        candidate_fks = detection.evidence.get("candidate_fks", [])
        return len(candidate_fks) == 1

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        candidate_fks = detection.evidence.get("candidate_fks", [])

        if len(candidate_fks) != 1:
            return None, f"Found {len(candidate_fks)} FK candidates; ambiguous, requires LLM fallback", 0.0

        fk_info = candidate_fks[0]
        s_tbl = fk_info.get("source_table")
        s_col = fk_info.get("source_column")
        t_tbl = fk_info.get("target_table")
        t_col = fk_info.get("target_column")

        # The old predicate
        old_pred = detection.location.predicate
        if old_pred:
            # Replace the old join predicate with the valid FK relationship
            new_pred = f"{s_tbl}.{s_col} = {t_tbl}.{t_col}"
            # Check if aliases were used
            pattern = re.compile(rf'\b{re.escape(old_pred)}\b', re.IGNORECASE)
            repaired = pattern.sub(new_pred, sql)
            if repaired != sql:
                return (
                    repaired,
                    f"{self.name}({old_pred} -> {new_pred})",
                    0.95
                )

        # Fallback: search for JOIN ... ON <condition>
        if s_tbl and t_tbl:
            join_pattern = re.compile(
                rf'(JOIN\s+(?:{s_tbl}|{t_tbl})\s+(?:AS\s+[a-zA-Z0-9_]+\s+)?ON\s+)([^;\n]+)',
                re.IGNORECASE
            )
            match = join_pattern.search(sql)
            if match:
                prefix = match.group(1)
                new_clause = f"{prefix}{s_tbl}.{s_col} = {t_tbl}.{t_col}"
                repaired = sql[:match.start()] + new_clause + sql[match.end():]
                return (
                    repaired,
                    f"{self.name}(Replaced JOIN ON condition with {s_tbl}.{s_col} = {t_tbl}.{t_col})",
                    0.94
                )

        return None, None, 0.0
