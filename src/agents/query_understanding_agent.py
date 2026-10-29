import re
from typing import Dict, List, Any, Optional
from src.agents.base_agent import BaseAgent
from src.models.state import GraphState, ConceptGroundingResult
from src.models.messages import AgentMessage, MessageType
from src.core.agent_registry import AgentDescriptor

from src.tools.intent_parser import NLPIntentParser
from src.tools.concept_grounder import ConceptGrounder

class QueryUnderstandingAgent(BaseAgent):
    """
    AGENT 1 — QueryUnderstandingAgent
    Role: Natural-language intent interpretation and initial conceptual grounding.
    Uses:
    - NLPIntentParser (src/tools/intent_parser.py)
    - ConceptGrounder (src/tools/concept_grounder.py)
    """
    def __init__(self, kb=None):
        super().__init__("QueryUnderstandingAgent", "Natural-language intent interpretation and conceptual grounding", kb=kb)
        self.intent_parser = NLPIntentParser()
        self.concept_grounder = ConceptGrounder(kb=kb)

    def get_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            name=self.name,
            role=self.role,
            capabilities=[
                "query_normalization",
                "intent_extraction",
                "temporal_interpretation",
                "filter_extraction",
                "business_context_grounding"
            ],
            tools=["nlp_intent_parser", "concept_grounder"],
            input_requirements=["original_request"],
            activation_conditions=["missing_concept_grounding"]
        )

    def observe(self, state: GraphState) -> None:
        self.concept_grounder.kb = self.kb

    def reason(self, state: GraphState) -> None:
        pass

    def evaluate_evidence(self, state: GraphState) -> float:
        if state.concept_grounding:
            return state.concept_grounding.confidence
        return 0.90

    def propose_action(self, state: GraphState) -> Optional[AgentMessage]:
        if state.concept_grounding is not None:
            return None

        query = (state.original_request or state.query or state.intent or "").strip()

        # 1. NLP Intent Parsing (Limits, Sort, Aggregations, Temporal, Filters)
        parsed_intent = self.intent_parser.parse_intent(query)
        normalized_query = parsed_intent["normalized_query"]
        aggregations = parsed_intent["aggregations"]
        sorting_requirements = parsed_intent["sorting_requirements"]
        temporal_constraints = parsed_intent["temporal_constraints"]
        filters = parsed_intent["filters"]
        limits = parsed_intent["limits"]
        comparison_requirements = parsed_intent.get("comparison_requirements", [])

        # 2. Concept Grounding (Entities, Metrics, Dimensions, Enterprise Glossary)
        dataset = state.dataset or "spider"
        database_id = state.database_id or state.database
        grounded = self.concept_grounder.ground_concepts(normalized_query, dataset=dataset, database_id=database_id)
        entities = grounded["entities"]
        concepts = grounded["concepts"]
        metrics = grounded["metrics"]
        dimensions = grounded["dimensions"]
        business_terms = grounded["business_terms"]
        ambiguous_terms = grounded.get("ambiguous_terms", [])

        # Log business rule evidence to state
        for b_dict in business_terms:
            state.knowledge_evidence.append({"type": "business_rule", "rule": b_dict})

        # Build ConceptGroundingResult
        confidence = 0.92 if (entities or metrics or aggregations) else 0.75
        result = ConceptGroundingResult(
            original_query=query,
            normalized_query=normalized_query,
            entities=entities,
            concepts=entities + metrics,
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            temporal_constraints=temporal_constraints,
            aggregations=aggregations,
            sorting_requirements=sorting_requirements,
            limits=limits,
            comparison_requirements=comparison_requirements,
            business_terms=business_terms,
            ambiguous_terms=ambiguous_terms,
            confidence=confidence,
            unresolved_concepts=[]
        )

        state.concept_grounding = result
        state.intent = query
        state.query = query

        summary_claim = (
            f"Understood intent: entities={entities}, metrics={metrics}, "
            f"aggregations={aggregations}, limit={limits}"
        )
        return AgentMessage(
            agent=self.name,
            message_type=MessageType.PROPOSAL,
            capability="Intent & Concept Grounding",
            claim=summary_claim,
            evidence=[result.dict()],
            confidence=confidence
        )
