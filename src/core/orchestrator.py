from typing import Any, Optional
from src.models.state import GraphState
from src.core.message_bus import MessageBus
from src.core.agent_registry import AgentRegistry
from src.core.decision_engine import DecisionEngine, ActionType
from src.knowledge.core.knowledge_base import KnowledgeBase

class Orchestrator:
    """
    Control-plane orchestrator for CG-SQL.
    Coordinates the dynamic interaction of the six intelligent agents using
    the DecisionEngine, shared GraphState blackboard, and MessageBus.
    """
    def __init__(self, registry: AgentRegistry, kb: Optional[KnowledgeBase] = None):
        self.registry = registry
        self.kb = kb
        self.message_bus = MessageBus()
        self.decision_engine = DecisionEngine()
        
    def run(self, initial_state: GraphState) -> GraphState:
        # Give kb to state and set state in message bus
        initial_state.database_id = initial_state.database
        self.message_bus.set_state(initial_state)
        state = initial_state
        
        while not state.is_terminated and state.iteration_count < state.max_iterations:
            state.iteration_count += 1
            
            # Decision Engine determines next action based on blackboard evidence
            next_action = self.decision_engine.decide_next_action(state)
            
            if next_action == ActionType.FINALIZE:
                state.is_terminated = True
                break
                
            # Map action to agent
            agent_name = self._map_action_to_agent(next_action)
            agent = self.registry.get_agent(agent_name)
            
            state.decision_history.append({
                "iteration": state.iteration_count,
                "action": next_action.value,
                "agent": agent_name
            })
            
            if agent:
                # Agent acts: observes blackboard, reasons, evaluates evidence, and proposes action
                message = agent.act(state)
                if message:
                    self.message_bus.publish(message)
            else:
                state.is_terminated = True
                break
                
        return state

    def _map_action_to_agent(self, action: ActionType) -> str:
        mapping = {
            ActionType.UNDERSTAND_QUERY: "QueryUnderstandingAgent",
            ActionType.GROUND_SCHEMA: "SchemaGroundingAgent",
            ActionType.GENERATE_SQL: "SQLGenerationAgent",
            ActionType.VALIDATE_EXECUTION: "ValidationExecutionAgent",
            ActionType.REPAIR_SQL: "RepairAgent",
            ActionType.HEDGE_RISK: "RiskHedgingAgent"
        }
        return mapping.get(action, "QueryUnderstandingAgent")

