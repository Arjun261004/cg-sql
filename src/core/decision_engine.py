from enum import Enum
from typing import Optional, List
from src.models.state import GraphState
from src.models.messages import AgentMessage, MessageType

class ActionType(str, Enum):
    UNDERSTAND_QUERY = "UNDERSTAND_QUERY"
    GROUND_SCHEMA = "GROUND_SCHEMA"
    GENERATE_SQL = "GENERATE_SQL"
    VALIDATE_EXECUTION = "VALIDATE_EXECUTION"
    REPAIR_SQL = "REPAIR_SQL"
    HEDGE_RISK = "HEDGE_RISK"
    FINALIZE = "FINALIZE"

class DecisionEngine:
    """
    Control-plane component: Evaluates GraphState blackboard and returns the next agent action.
    Maintains authority to dynamically route execution, retry, repair, re-plan, or terminate.
    """
    def decide_next_action(self, state: GraphState) -> ActionType:
        # 1. Termination condition
        if state.is_terminated or state.iteration_count >= state.max_iterations:
            return ActionType.FINALIZE

        # 2. Check if an agent explicitly requested a specific target agent
        if state.agent_messages and state.agent_messages[-1].target_agents:
            target = state.agent_messages[-1].target_agents[0]
            if target == "ValidationExecutionAgent" and state.selected_candidate:
                # Only if not already validated in current state
                if not state.selected_candidate.get("validation"):
                    return ActionType.VALIDATE_EXECUTION
            elif target == "SchemaGroundingAgent" and not state.schema_linking:
                return ActionType.GROUND_SCHEMA
            elif target == "SQLGenerationAgent":
                return ActionType.GENERATE_SQL

        # 3. Query Understanding check
        if state.concept_grounding is None:
            return ActionType.UNDERSTAND_QUERY

        # 4. Schema Grounding check
        if state.schema_linking is None:
            return ActionType.GROUND_SCHEMA

        # 5. SQL Generation check
        if not state.sql_candidates:
            return ActionType.GENERATE_SQL

        # 6. Validation / Execution check
        current_cand = state.selected_candidate or state.sql_candidates[0]
        cand_validated = bool(current_cand.get("validation"))
        if not cand_validated:
            return ActionType.VALIDATE_EXECUTION

        # 7. Check validation outcome
        last_val = state.validation_result
        last_exec = state.execution_results[-1] if state.execution_results else {}
        is_failure = bool(last_exec.get("error")) or (last_val and not last_val.execution_success)

        if is_failure:
            # Check if repair budget is available
            if len(state.repair_history) < 3 and not getattr(state, "mapledoctor_verified", False):
                # If latest candidate failed and hasn't been repaired yet
                repairs_matching = [
                    r for r in state.repair_history
                    if r.get("original_sql") == current_cand.get("sql")
                ]
                if not repairs_matching:
                    return ActionType.REPAIR_SQL
            
            # If repair budget exceeded or already repaired/diagnosed, proceed to risk hedging evaluation
            if not state.risk_evaluation:
                return ActionType.HEDGE_RISK
            return ActionType.FINALIZE

        # 8. Execution succeeded -> MapleDoctor inspection (RepairAgent)
        if not getattr(state, "mapledoctor_verified", False):
            return ActionType.REPAIR_SQL

        # 9. Execution succeeded -> evaluate candidates via RiskHedgingAgent
        if not state.risk_evaluation:
            return ActionType.HEDGE_RISK

        # 10. Finalized
        return ActionType.FINALIZE

