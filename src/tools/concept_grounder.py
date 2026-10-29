from typing import Dict, List, Any, Optional
from src.knowledge.core.knowledge_base import KnowledgeBase

class ConceptGrounder:
    """
    Concept Grounder tool for QueryUnderstandingAgent.
    Maps natural language tokens to business concepts, entities, metrics, and dimensions,
    using KnowledgeBase business definitions and deterministic vocabularies.
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb

        self.entity_keywords = [
            "customer", "customers", "order", "orders", "department", "departments",
            "account", "accounts", "user", "users", "employee", "employees",
            "student", "students", "flight", "flights", "aircraft", "aircrafts",
            "pilot", "pilots", "airport", "airports", "match", "matches", "plane", "planes",
            "course", "courses", "head", "heads", "musical", "musicals", "actor", "actors",
            "singer", "singers", "concert", "concerts", "car", "cars"
        ]

        self.metric_keywords = [
            "revenue", "sales", "salary", "amount", "budget", "cost", "price", "count",
            "score", "points", "duration", "capacity", "weight", "height", "distance", "age"
        ]

        self.dimension_keywords = [
            "name", "id", "city", "state", "category", "type", "date", "status",
            "country", "gender", "award", "title", "role", "year", "genre", "course",
            "age", "model"
        ]

    def ground_concepts(
        self,
        normalized_query: str,
        dataset: str = "spider",
        database_id: str = ""
    ) -> Dict[str, Any]:
        words = normalized_query.split()
        entities: List[str] = []
        concepts: List[str] = []
        metrics: List[str] = []
        dimensions: List[str] = []
        business_terms: List[Dict[str, Any]] = []

        # Dynamic schema discovery from KB if available
        if self.kb and database_id:
            try:
                db_schema = self.kb.get_schema(dataset, database_id)
                if db_schema and db_schema.tables:
                    for t_name, t_meta in db_schema.tables.items():
                        t_lower = t_name.lower()
                        # check if table or plural in query
                        if t_lower in words or f"{t_lower}s" in words or t_lower in normalized_query:
                            matched_word = next((w for w in words if w in [t_lower, f"{t_lower}s"]), t_lower)
                            if matched_word not in entities:
                                entities.append(matched_word)
                                concepts.append(matched_word)
                        for c_name in t_meta.columns.keys():
                            c_lower = c_name.lower()
                            if c_lower in words or c_lower in normalized_query:
                                if c_lower not in dimensions and c_lower not in metrics:
                                    dimensions.append(c_lower)
                                    concepts.append(c_lower)
            except Exception:
                pass

        for w in words:
            if w in self.entity_keywords and w not in entities:
                entities.append(w)
                concepts.append(w)

            # Query KB for canonical enterprise definitions
            if self.kb:
                b_def = self.kb.get_business_definition(w)
                if b_def:
                    b_dict = b_def.dict() if hasattr(b_def, "dict") else b_def
                    business_terms.append(b_dict)

        for m in self.metric_keywords:
            if m in normalized_query and m not in metrics:
                metrics.append(m)
                concepts.append(m)

        for d in self.dimension_keywords:
            if d in normalized_query and d not in dimensions:
                dimensions.append(d)
                concepts.append(d)

        return {
            "entities": entities,
            "concepts": concepts,
            "metrics": metrics,
            "dimensions": dimensions,
            "business_terms": business_terms,
            "ambiguous_terms": []
        }
