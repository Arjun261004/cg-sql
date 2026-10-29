from typing import List, Optional
from src.models.state import GraphState
from src.models.messages import AgentMessage, MessageType
from src.core.agent_registry import AgentDescriptor
from src.knowledge.core.knowledge_base import KnowledgeBase

class BaseAgent:
    def __init__(self, name: str, role: str, kb: Optional[KnowledgeBase] = None):
        self.name = name
        self.role = role
        self.kb = kb
        
    def get_descriptor(self) -> AgentDescriptor:
        raise NotImplementedError("Subclasses must implement get_descriptor")

    def observe(self, state: GraphState) -> None:
        """Observe the current shared state."""
        pass

    def reason(self, state: GraphState) -> None:
        """Form internal reasoning based on state."""
        pass

    def evaluate_evidence(self, state: GraphState) -> float:
        """Evaluate evidence and return a confidence score (0.0 to 1.0)."""
        return 0.0

    def propose_action(self, state: GraphState) -> Optional[AgentMessage]:
        """Produce a proposed action/decision as an AgentMessage."""
        return None
        
    def act(self, state: GraphState) -> Optional[AgentMessage]:
        """Main entry point for the agent to observe, reason, evaluate, and propose."""
        self.observe(state)
        self.reason(state)
        confidence = self.evaluate_evidence(state)
        
        # Agents update state by returning messages, which are processed by the message bus / coordinator
        message = self.propose_action(state)
        if message:
            message.confidence = confidence
            message.agent = self.name
        return message
