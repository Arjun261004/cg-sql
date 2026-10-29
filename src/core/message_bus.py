from typing import List, Optional
from src.models.state import GraphState
from src.models.messages import AgentMessage, MessageType

class MessageBus:
    """
    Handles distribution of messages to agents.
    For simplicity in this POC, the message bus updates the graph state
    and allows agents to query the blackboard.
    """
    def __init__(self):
        self.state: Optional[GraphState] = None
        
    def set_state(self, state: GraphState):
        self.state = state
        
    def publish(self, message: AgentMessage):
        if self.state:
            self.state.add_message(message)
