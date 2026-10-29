from typing import Dict, List, Any, Optional
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.models.state import ConceptGroundingResult

class ERReasoner:
    """
    Internal E/R reasoning engine for SchemaGroundingAgent.
    Reasons conceptually over entity meanings, relationships, join paths,
    cardinality, and duplicate-row risks using KB relationship facts and LLM semantic disambiguation.
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb

    def resolve_join_paths(
        self,
        dataset: str,
        database_id: str,
        candidate_tables: List[str]
    ) -> List[List[Dict[str, Any]]]:
        """Finds deterministic join paths between candidate tables via KB relationship graph."""
        join_paths = []
        if not self.kb or len(candidate_tables) < 2:
            return join_paths

        # Pairwise search for join paths
        for i in range(len(candidate_tables)):
            for j in range(i + 1, len(candidate_tables)):
                t_a = candidate_tables[i]
                t_b = candidate_tables[j]
                paths = self.kb.find_join_paths(dataset, database_id, t_a, t_b)
                for p in paths:
                    path_dicts = [r.dict() if hasattr(r, "dict") else r for r in p]
                    if path_dicts not in join_paths:
                        join_paths.append(path_dicts)

        return join_paths

    def analyze_er_structure(
        self,
        dataset: str,
        database_id: str,
        candidate_tables: List[str],
        intent: str,
        concept_grounding: Optional[ConceptGroundingResult] = None
    ) -> Dict[str, Any]:
        """
        Analyzes relationship semantics, cardinality, and duplicate-row risk.
        """
        join_paths = self.resolve_join_paths(dataset, database_id, candidate_tables)
        
        # Analyze cardinality and duplicate-row risk
        duplicate_risks = []
        relationships_found = []
        if self.kb:
            all_rels = self.kb.get_relationships(dataset, database_id)
            for rel in all_rels:
                r_dict = rel.dict() if hasattr(rel, "dict") else rel
                if r_dict["source_table"] in candidate_tables and r_dict["target_table"] in candidate_tables:
                    relationships_found.append(r_dict)
                    # Foreign key from A to B: joining A (many) to B (one) is 1-to-many if starting from B
                    if r_dict.get("relationship_type") == "foreign_key":
                        duplicate_risks.append({
                            "join": f"{r_dict['source_table']} -> {r_dict['target_table']}",
                            "risk": "Parent row duplication if grouping/distinct is omitted"
                        })

        # Conceptual model derivation
        conceptual_model = {
            "primary_entity": candidate_tables[0] if candidate_tables else "unknown",
            "related_entities": candidate_tables[1:] if len(candidate_tables) > 1 else [],
            "join_paths_count": len(join_paths),
            "duplicate_risks": duplicate_risks
        }

        # Optional LLM semantic disambiguation if multiple tables exist
        if len(candidate_tables) > 1 and intent:
            try:
                from src.core.llm_client import LLMClient
                llm = LLMClient()
                prompt = f"""
                Given candidate database tables: {candidate_tables}
                Discovered Join Paths: {join_paths}
                User Intent: "{intent}"
                
                Reason conceptually about the primary entity and the relationship needed.
                Output ONLY a JSON object: {{"primary_entity": "...", "relationship_meaning": "...", "recommended_path": "..."}}
                """
                llm_result = llm.generate_json(prompt)
                if llm_result and isinstance(llm_result, dict):
                    conceptual_model.update(llm_result)
            except Exception as e:
                # LLM optional fallback
                pass

        return {
            "conceptual_model": conceptual_model,
            "join_paths": join_paths,
            "relationships": relationships_found,
            "duplicate_risks": duplicate_risks
        }

