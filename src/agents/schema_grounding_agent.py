from typing import Dict, List, Any, Optional
from src.agents.base_agent import BaseAgent
from src.models.state import GraphState, SchemaLinkingResult
from src.models.messages import AgentMessage, MessageType
from src.core.agent_registry import AgentDescriptor
from src.tools.schema_linker import BidirectionalSchemaLinker, SchemaPruner
from src.tools.er_reasoner import ERReasoner

class SchemaGroundingAgent(BaseAgent):
    """
    AGENT 2 — SchemaGroundingAgent
    Role: Translate conceptual user intent into grounded database concepts.
    Absorbs:
    - current Schema Agent
    - bidirectional schema linker (Forward & Backward linking)
    - ER Reasoner (relationship graph reasoning, cardinality, join-path discovery)
    - schema retrieval & Knowledge Base facts
    - schema pruning (full relevant schema vs pruned minimal schema)
    - schema confidence calculation
    """
    def __init__(self, kb=None):
        super().__init__("SchemaGroundingAgent", "Bidirectional schema linking and E/R conceptual grounding", kb=kb)
        self.linker = BidirectionalSchemaLinker(kb=kb)
        self.er_reasoner = ERReasoner(kb=kb)
        self.pruner = SchemaPruner()

    def get_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            name=self.name,
            role=self.role,
            capabilities=[
                "forward_schema_linking",
                "backward_schema_validation",
                "er_reasoning",
                "schema_pruning",
                "join_path_discovery"
            ],
            tools=["bidirectional_schema_linker", "er_reasoner", "schema_pruner"],
            input_requirements=["concept_grounding"],
            activation_conditions=["missing_schema_linking"]
        )

    def observe(self, state: GraphState) -> None:
        self.linker.kb = self.kb
        self.er_reasoner.kb = self.kb

    def reason(self, state: GraphState) -> None:
        pass

    def evaluate_evidence(self, state: GraphState) -> float:
        if state.schema_linking:
            return state.schema_linking.confidence
        return 0.85

    def propose_action(self, state: GraphState) -> Optional[AgentMessage]:
        if state.schema_linking is not None:
            return None

        dataset = "spider"
        database_id = state.database_id or state.database

        # 1. FORWARD LINKING: Intent / Concepts -> Candidate Schema
        forward_res = self.linker.forward_link(
            dataset=dataset,
            database_id=database_id,
            concept_grounding=state.concept_grounding,
            intent=state.intent
        )
        candidate_tables_meta = forward_res["candidate_tables"]
        candidate_columns = forward_res["candidate_columns"]
        concept_mappings = forward_res["concept_mappings"]
        unmatched_concepts = forward_res["unmatched_concepts"]
        candidate_table_names = [t["table"] for t in candidate_tables_meta if "table" in t]

        # Log search evidence to blackboard
        if forward_res.get("search_results"):
            state.knowledge_evidence.append({
                "type": "schema_search",
                "results": forward_res["search_results"]
            })

        # 2. ER REASONING: Analyze relationship graph & join paths
        er_res = self.er_reasoner.analyze_er_structure(
            dataset=dataset,
            database_id=database_id,
            candidate_tables=candidate_table_names,
            intent=state.intent,
            concept_grounding=state.concept_grounding
        )
        join_paths = er_res["join_paths"]
        relationships = er_res["relationships"]
        conceptual_model = er_res["conceptual_model"]

        if join_paths:
            state.knowledge_evidence.append({
                "type": "join_paths",
                "paths": join_paths
            })

        # 3. BACKWARD LINKING: Selected schema -> expressible concepts vs user intent
        backward_res = self.linker.backward_validate(
            dataset=dataset,
            database_id=database_id,
            candidate_tables=candidate_table_names,
            candidate_columns=candidate_columns,
            concept_grounding=state.concept_grounding,
            intent=state.intent
        )
        ambiguous_mappings = backward_res["ambiguous_mappings"]
        confidence = backward_res["backward_confidence"]

        # 4. SCHEMA PRUNING: Produce full schema candidate & pruned schema candidate
        full_candidate, pruned_candidate, rejected = self.pruner.prune(
            kb=self.kb,
            dataset=dataset,
            database_id=database_id,
            candidate_tables=candidate_tables_meta,
            candidate_columns=candidate_columns,
            active_join_paths=join_paths
        )

        final_tables = pruned_candidate["tables"]
        final_columns = pruned_candidate["columns"]

        result = SchemaLinkingResult(
            final_tables=final_tables,
            final_columns=final_columns,
            relationships=relationships,
            join_paths=join_paths,
            concept_mappings=concept_mappings,
            unmatched_concepts=unmatched_concepts,
            ambiguous_mappings=ambiguous_mappings,
            confidence=confidence,
            provenance={"dataset": dataset, "database_id": database_id, "rejected": rejected},
            full_schema_candidate=full_candidate,
            pruned_schema_candidate=pruned_candidate
        )

        # Store in state
        state.schema_linking = result
        state.schema_candidates = candidate_tables_meta
        state.conceptual_model = conceptual_model
        state.er_context = {
            "relationships": relationships,
            "join_paths": join_paths,
            "duplicate_risks": er_res["duplicate_risks"]
        }

        # Check if confidence is too low or severe ambiguity exists
        if confidence < 0.60 or len(unmatched_concepts) > 0:
            return AgentMessage(
                agent=self.name,
                message_type=MessageType.OBJECTION,
                capability="Bidirectional Linking & ER Reasoning",
                claim=f"Low schema confidence ({confidence:.2f}): Unmatched concepts: {unmatched_concepts}. Requested attributes/entities not found in database '{database_id}'.",
                evidence=[result.dict()],
                confidence=confidence
            )

        claim_text = (
            f"Grounded schema via bidirectional linking: tables={final_tables}, "
            f"join_paths={len(join_paths)}, confidence={confidence:.2f}"
        )
        return AgentMessage(
            agent=self.name,
            message_type=MessageType.PROPOSAL,
            capability="Bidirectional Linking & ER Reasoning",
            claim=claim_text,
            evidence=[result.dict()],
            confidence=confidence
        )
