from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class MessageType(str, Enum):
    PROPOSAL = "proposal"
    OBJECTION = "objection"
    REQUEST = "request"
    EVIDENCE = "evidence"
    DECISION = "decision"
    REJECTION = "rejection"

class AgentMessage(BaseModel):
    agent: str
    message_type: MessageType
    claim: str
    capability: str = ""  # Internal capability/module name
    evidence: List[Any] = Field(default_factory=list)
    confidence: float = 0.0
    recommended_action: Optional[str] = None
    requires_response: bool = False
    target_agents: List[str] = Field(default_factory=list)

    def __str__(self):
        targets = f" -> {','.join(self.target_agents)}" if self.target_agents else ""
        cap = f" [{self.capability}]" if self.capability else ""
        return f"[{self.agent.upper()}{cap}{targets}] {self.message_type.upper()}: {self.claim} (Confidence: {self.confidence})"
