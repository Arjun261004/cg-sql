import re
from typing import Optional, Tuple, List, Dict, Any
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules.base import MapleRule
from src.mapledoctor.ast_utils import parse_sql, extract_tables_and_aliases

class MissingJoinRule(MapleRule):
    """
    Rule 5: MISSING JOIN
    The query references a column belonging to a table that has not been joined.
    
    Paper Logic:
    IF a clear foreign-key relationship exists:
        Add the missing table using the appropriate JOIN.
    IF:
        - no foreign key exists
        OR
        - multiple candidate foreign keys exist
    THEN:
        Invoke the LLM repairer. Do not invent JOIN relationships.
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.MISSING_JOIN

    @property
    def name(self) -> str:
        return "MapleDoctor_Rule5_MissingJoin"

    def can_repair(self, detection: DetectionResult) -> bool:
        if detection.category != ErrorCategory.MISSING_JOIN:
            return False
        return bool(detection.is_rule_applicable and detection.evidence.get("fk_paths_count") == 1)

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        kb: Optional[KnowledgeBase] = None
    ) -> Tuple[Optional[str], Optional[str], float]:
        unjoined_table = detection.evidence.get("unjoined_table")
        col_name = detection.evidence.get("column")

        if not unjoined_table or not kb:
            return None, "Missing unjoined table metadata; requires LLM fallback", 0.0

        tree = parse_sql(sql, dialect=dialect)
        tables_and_aliases = extract_tables_and_aliases(tree) if tree else {}
        current_tables = list(tables_and_aliases.keys())

        # Find foreign key paths connecting unjoined_table to current_tables
        candidate_paths = []
        for q_tbl in current_tables:
            paths = kb.find_join_paths(dataset, database_id, unjoined_table, q_tbl)
            for p in paths:
                candidate_paths.append((unjoined_table, q_tbl, p))

        if len(candidate_paths) != 1:
            return None, f"Found {len(candidate_paths)} candidate join paths; ambiguous, requires LLM fallback", 0.0

        # Exactly 1 foreign key path
        src_tbl, tgt_tbl, rel_list = candidate_paths[0]
        if not rel_list:
            return None, "Empty relationship path; requires LLM fallback", 0.0

        rel = rel_list[0]
        r_dict = rel.model_dump() if hasattr(rel, "model_dump") else (rel.dict() if hasattr(rel, "dict") else rel)
        s_col = r_dict.get("source_column")
        t_col = r_dict.get("target_column")
        s_tbl = r_dict.get("source_table")
        t_tbl = r_dict.get("target_table")

        # Resolve alias of the target table if present in query
        tgt_alias = tables_and_aliases.get(t_tbl.lower(), t_tbl)
        join_clause = f"JOIN {unjoined_table} ON {s_tbl}.{s_col} = {tgt_alias}.{t_col}"

        # Insert JOIN before WHERE / GROUP BY / ORDER BY or at end of FROM
        if re.search(r'\bWHERE\b', sql, re.IGNORECASE):
            repaired = re.sub(r'(\bWHERE\b)', f"{join_clause} \\1", sql, count=1, flags=re.IGNORECASE)
        elif re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
            repaired = re.sub(r'(\bGROUP\s+BY\b)', f"{join_clause} \\1", sql, count=1, flags=re.IGNORECASE)
        elif re.search(r'\bORDER\s+BY\b', sql, re.IGNORECASE):
            repaired = re.sub(r'(\bORDER\s+BY\b)', f"{join_clause} \\1", sql, count=1, flags=re.IGNORECASE)
        else:
            repaired = f"{sql} {join_clause}"

        return (
            repaired,
            f"{self.name}(Add {join_clause})",
            0.94
        )
