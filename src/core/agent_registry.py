from typing import Dict, List, Any
from pydantic import BaseModel

class AgentDescriptor(BaseModel):
    name: str
    role: str
    capabilities: List[str]
    tools: List[str]
    input_requirements: List[str]
    activation_conditions: List[str]

class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, Any] = {}
        self._descriptors: Dict[str, AgentDescriptor] = {}

    def register(self, agent_instance: Any, descriptor: AgentDescriptor):
        self._agents[descriptor.name] = agent_instance
        self._descriptors[descriptor.name] = descriptor

    def get_agent(self, name: str) -> Any:
        return self._agents.get(name)

    def get_descriptor(self, name: str) -> AgentDescriptor:
        return self._descriptors.get(name)

    def list_agents(self) -> List[AgentDescriptor]:
        return list(self._descriptors.values())
