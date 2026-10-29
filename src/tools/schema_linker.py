from typing import Dict, List, Any, Optional, Tuple
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.models.state import ConceptGroundingResult

class BidirectionalSchemaLinker:
    """
    True Bidirectional Schema Linker for SchemaGroundingAgent.
    Forward Linking: User concepts -> candidate tables, columns, relationships.
    Backward Linking: Selected schema -> expressible concepts vs user intent,
                     detecting missing, unsupported, or ambiguous concepts.
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb

    def forward_link(
        self,
        dataset: str,
        database_id: str,
        concept_grounding: Optional[ConceptGroundingResult],
        intent: str
    ) -> Dict[str, Any]:
        """Maps user concepts to candidate schema elements."""
        candidate_tables: List[Dict[str, Any]] = []
        candidate_columns: Dict[str, List[str]] = {}
        concept_mappings: Dict[str, str] = {}
        unmatched_concepts: List[str] = []
        
        search_query = intent
        if concept_grounding:
            terms = concept_grounding.entities + concept_grounding.metrics + concept_grounding.dimensions
            if terms:
                search_query = " ".join(terms)

        search_results = {"tables": [], "columns": []}
        if self.kb:
            search_results = self.kb.search_schema(dataset, database_id, search_query)
            
            # Map discovered tables
            for t in search_results.get("tables", []):
                t_name = t["name"]
                score = t.get("score", 0.8)
                cols = [c.name for c in self.kb.get_columns(dataset, database_id, t_name)]
                candidate_tables.append({"table": t_name, "columns": cols, "confidence": score})
                candidate_columns[t_name] = cols
                concept_mappings[t_name] = t_name

            # Map discovered columns
            for col in search_results.get("columns", []):
                col_name = col["name"]
                t_name = col["table"]
                concept_mappings[col_name] = f"{t_name}.{col_name}"
                if t_name not in candidate_columns:
                    candidate_columns[t_name] = []
                if col_name not in candidate_columns[t_name]:
                    candidate_columns[t_name].append(col_name)
                    
                if not any(c.get("table") == t_name for c in candidate_tables):
                    candidate_tables.append({"table": t_name, "columns": [col_name], "confidence": col.get("score", 0.7)})

        # Fallback if no tables found via search
        if not candidate_tables and self.kb:
            full_schema = self.kb.get_schema(dataset, database_id)
            if full_schema and full_schema.tables:
                for t_name, t_schema in list(full_schema.tables.items())[:3]:
                    cols = list(t_schema.columns.keys())
                    candidate_tables.append({"table": t_name, "columns": cols, "confidence": 0.3})
                    candidate_columns[t_name] = cols

        # Identify unmatched concepts against full database schema
        if concept_grounding:
            db_all = set()
            if self.kb:
                full_schema = self.kb.get_schema(dataset, database_id)
                if full_schema and full_schema.tables:
                    for t_name, t_schema in full_schema.tables.items():
                        db_all.add(t_name.lower())
                        for c_name in t_schema.columns.keys():
                            db_all.add(c_name.lower())
            if not db_all:
                for t in candidate_tables:
                    db_all.add(t["table"].lower())
                for t_cols in candidate_columns.values():
                    for c in t_cols:
                        db_all.add(c.lower())

            for ent in concept_grounding.entities:
                ent_clean = ent.lower()
                ent_stem = ent_clean[:-1] if ent_clean.endswith("s") else ent_clean
                matched = (
                    ent_clean in db_all
                    or ent_stem in db_all
                    or any(ent_clean in k or ent_stem in k or k in ent_clean for k in db_all)
                )
                if not matched:
                    unmatched_concepts.append(ent)

            for filt in concept_grounding.filters:
                term = filt.get("field", "")
                if term:
                    term_clean = term.lower()
                    term_stem = term_clean[:-1] if term_clean.endswith("s") else term_clean
                    matched = (
                        term_clean in db_all
                        or term_stem in db_all
                        or any(term_clean in k or term_stem in k or k in term_clean for k in db_all)
                    )
                    if not matched and term not in unmatched_concepts:
                        unmatched_concepts.append(term)

        return {
            "candidate_tables": candidate_tables,
            "candidate_columns": candidate_columns,
            "concept_mappings": concept_mappings,
            "unmatched_concepts": unmatched_concepts,
            "search_results": search_results
        }

    def backward_validate(
        self,
        dataset: str,
        database_id: str,
        candidate_tables: List[str],
        candidate_columns: Dict[str, List[str]],
        concept_grounding: Optional[ConceptGroundingResult],
        intent: str
    ) -> Dict[str, Any]:
        """
        Reasons backwards:
        Given candidate schema -> what concepts can it actually express?
        Checks if required entities, metrics, and filters are supported.
        """
        expressible_concepts: List[str] = []
        unsupported_concepts: List[str] = []
        ambiguous_mappings: List[Dict[str, Any]] = []

        all_cols = []
        for t, cols in candidate_columns.items():
            all_cols.extend([f"{t}.{c}".lower() for c in cols])
            all_cols.extend([c.lower() for c in cols])

        table_names = [t.lower() for t in candidate_tables]

        if concept_grounding:
            for ent in concept_grounding.entities:
                ent_clean = ent.lower()
                ent_stem = ent_clean[:-1] if ent_clean.endswith("s") else ent_clean
                found = (
                    any(ent_clean in tbl or ent_stem in tbl or tbl in ent_clean for tbl in table_names)
                    or any(ent_clean in col or ent_stem in col or col in ent_clean for col in all_cols)
                )
                if found:
                    expressible_concepts.append(ent)
                else:
                    unsupported_concepts.append(ent)

            for metric in concept_grounding.metrics:
                m_clean = metric.lower()
                m_stem = m_clean[:-1] if m_clean.endswith("s") else m_clean
                found = any(m_clean in col or m_stem in col or col in m_clean for col in all_cols)
                if found:
                    expressible_concepts.append(metric)
                else:
                    unsupported_concepts.append(metric)

            for dim in concept_grounding.dimensions:
                d_clean = dim.lower()
                d_stem = d_clean[:-1] if d_clean.endswith("s") else d_clean
                found = (
                    any(d_clean in col or d_stem in col or col in d_clean for col in all_cols)
                    or any(d_clean in tbl or d_stem in tbl or tbl in d_clean for tbl in table_names)
                )
                if found:
                    expressible_concepts.append(dim)
                else:
                    unsupported_concepts.append(dim)

            for filt in concept_grounding.filters:
                term = filt.get("field", "")
                if term:
                    t_clean = term.lower()
                    t_stem = t_clean[:-1] if t_clean.endswith("s") else t_clean
                    found = any(t_clean in col or t_stem in col or col in t_clean for col in all_cols)
                    if found:
                        expressible_concepts.append(term)
                    else:
                        unsupported_concepts.append(term)
                        ambiguous_mappings.append({"field": term, "reason": "No direct column match in selected schema"})

        # Confidence calculation
        total_concepts = len(expressible_concepts) + len(unsupported_concepts)
        if total_concepts > 0:
            if len(expressible_concepts) == 0:
                confidence = 0.10
            else:
                confidence = max(0.20, len(expressible_concepts) / total_concepts)
        else:
            confidence = 0.85 if candidate_tables else 0.4

        return {
            "expressible_concepts": expressible_concepts,
            "unsupported_concepts": unsupported_concepts,
            "ambiguous_mappings": ambiguous_mappings,
            "backward_confidence": confidence
        }

class SchemaPruner:
    """
    Produces both a full relevant schema candidate and a pruned minimal schema candidate.
    Identifies rejected candidates and reasons for rejection.
    """
    def prune(
        self,
        kb: Optional[KnowledgeBase],
        dataset: str,
        database_id: str,
        candidate_tables: List[Dict[str, Any]],
        candidate_columns: Dict[str, List[str]],
        active_join_paths: List[Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
        """
        Returns:
            full_schema_candidate: all candidate tables and columns
            pruned_schema_candidate: minimal set needed for query
            rejected_candidates: list of rejected tables/columns with reasons
        """
        # Full schema candidate retains all discovered tables
        full_tables = [c.get("table") for c in candidate_tables if "table" in c]
        full_candidate = {
            "tables": full_tables,
            "columns": candidate_columns,
            "type": "full_schema"
        }

        # Pruned schema candidate keeps only essential tables connected by join paths
        essential_tables = set()
        if active_join_paths:
            for path in active_join_paths:
                for rel in path:
                    if isinstance(rel, dict):
                        essential_tables.add(rel.get("source_table"))
                        essential_tables.add(rel.get("target_table"))
                    elif hasattr(rel, "source_table"):
                        essential_tables.add(rel.source_table)
                        essential_tables.add(rel.target_table)

        if not essential_tables:
            # Keep highest confidence tables (up to 2)
            sorted_tables = sorted(candidate_tables, key=lambda x: x.get("confidence", 0), reverse=True)
            essential_tables = set(c["table"] for c in sorted_tables[:2] if "table" in c)

        pruned_tables = [t for t in full_tables if t in essential_tables]
        pruned_columns = {t: cols for t, cols in candidate_columns.items() if t in essential_tables}

        # Rejected candidates
        rejected = []
        for t in full_tables:
            if t not in essential_tables:
                rejected.append({
                    "table": t,
                    "reason": "Not on active join path and low direct relevance to query intent"
                })

        pruned_candidate = {
            "tables": pruned_tables if pruned_tables else full_tables,
            "columns": pruned_columns if pruned_columns else candidate_columns,
            "type": "pruned_schema"
        }

        return full_candidate, pruned_candidate, rejected

