import json
from src.core.agent_registry import AgentRegistry
from src.core.orchestrator import Orchestrator
from src.models.state import GraphState
from src.agents import (
    QueryUnderstandingAgent,
    SchemaGroundingAgent,
    SQLGenerationAgent,
    ValidationExecutionAgent,
    RepairAgent,
    RiskHedgingAgent
)
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.knowledge.core.repository import KnowledgeRepository

def setup_registry(kb=None) -> AgentRegistry:
    """Registers exactly the six intelligent agents in the CG-SQL multi-agent system."""
    registry = AgentRegistry()
    agents = [
        QueryUnderstandingAgent(kb=kb),
        SchemaGroundingAgent(kb=kb),
        SQLGenerationAgent(kb=kb),
        ValidationExecutionAgent(kb=kb),
        RepairAgent(kb=kb),
        RiskHedgingAgent(kb=kb)
    ]
    for agent in agents:
        agent.kb = kb
        registry.register(agent, agent.get_descriptor())
    return registry

def run_example(name: str, request: str, dialect: str = "SQLite", database: str = "department_management"):
    print(f"\n{'='*50}\nRUNNING EXAMPLE: {name}\n{'='*50}")
    print(f"USER: {request}\n")
    
    kb_repo = KnowledgeRepository()
    kb = KnowledgeBase(kb_repo)
    
    registry = setup_registry(kb=kb)
    orchestrator = Orchestrator(registry, kb=kb)
    
    initial_state = GraphState(
        original_request=request,
        intent=request,
        dialect=dialect,
        database=database,
        db_path=f"spider_data/database/{database}/{database}.sqlite" if database != "default" else ""
    )
    
    final_state = orchestrator.run(initial_state)
    
    print("--- TRACE ---")
    for msg in final_state.trace:
        print(msg)
    
    print("\n--- FINAL RESULT ---")
    print(f"SQL: {final_state.final_sql}")
    print(f"Confidence: {final_state.final_confidence}")
    print(f"Answer: {final_state.final_answer}")
    if final_state.risk_evaluation:
        print(f"Risk Hedging: {final_state.risk_evaluation.decision_rationale}")

if __name__ == "__main__":
    # Example 1: Spider Query (department_management)
    run_example("1. Standard Spider Query", "How many departments have a budget greater than 500000?", database="department_management")
    
    # Example 2: Complex Query with Ranking & Aggregation
    run_example("2. Ranking & Aggregation Query", "Which department has the highest budget in 2025?", database="department_management")
    
    # Example 3: Repair Scenario with Dialect Date Function Mismatch
    run_example("3. Self-Repair Scenario (Snowflake Dialect)", "Show monthly sales for 2025 using DATE_TRUNC.", dialect="Snowflake")

