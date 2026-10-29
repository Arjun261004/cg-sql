import pytest
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.knowledge.core.repository import KnowledgeRepository
from src.tools.database_executor import DatabaseExecutor
from src.mapledoctor.engine import MapleDoctorEngine
from src.models.state import GraphState, ValidationResult
from src.agents.repair_agent import RepairAgent
from src.core.agent_registry import AgentRegistry
from main import setup_registry

class MockLLMClient:
    def __init__(self, fixed_response: str = ""):
        self.fixed_response = fixed_response

    def generate_text(self, prompt: str) -> str:
        return self.fixed_response

@pytest.fixture
def kb():
    repo = KnowledgeRepository()
    return KnowledgeBase(repo)

@pytest.fixture
def executor(kb):
    return DatabaseExecutor(kb=kb)

# 1. SQL generation -> MapleDoctor
def test_integration_sql_gen_to_mapledoctor(kb):
    engine = MapleDoctorEngine(kb=kb)
    # Generated candidate SQL with implicit integer division
    generated_sql = "SELECT COUNT(*) / 12 FROM department"
    result = engine.diagnose_and_repair(
        sql=generated_sql,
        question="What is the average number of departments per month?",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "CAST(COUNT(*) AS REAL)" in result.final_sql

# 2. SQL generation -> execution
def test_integration_sql_gen_to_execution(kb, executor):
    generated_sql = "SELECT Name, Budget_in_Billions FROM department WHERE Ranking = 1"
    exec_res = executor.execute(
        sql=generated_sql,
        dialect="SQLite",
        db_path="spider_data/database/department_management/department_management.sqlite",
        dataset="spider",
        database_id="department_management"
    )
    assert exec_res["status"] == "success"
    assert exec_res["rows"] > 0

# 3. SQL generation -> MapleDoctor -> execution
def test_integration_sql_gen_to_mapledoctor_to_execution(kb, executor):
    engine = MapleDoctorEngine(kb=kb, executor=executor)
    # Generated SQL with function hallucination DIVIDE
    generated_sql = "SELECT DIVIDE(Budget_in_Billions, 2) FROM department WHERE Ranking = 1"
    
    # First: MapleDoctor diagnoses and repairs
    result = engine.diagnose_and_repair(
        sql=generated_sql,
        error_text="no such function: DIVIDE",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite",
        db_path="spider_data/database/department_management/department_management.sqlite"
    )
    assert result.was_repaired
    
    # Second: Execute the repaired SQL
    exec_res = executor.execute(
        sql=result.final_sql,
        dialect="SQLite",
        db_path="spider_data/database/department_management/department_management.sqlite"
    )
    assert exec_res["status"] == "success"
    assert exec_res["rows"] == 1

# 4. Rule-based repair flow via RepairAgent
def test_integration_rule_based_repair_agent(kb):
    agent = RepairAgent(kb=kb)
    state = GraphState(
        original_request="Count departments divided by 12",
        database="department_management",
        database_id="department_management",
        dialect="SQLite",
        db_path="spider_data/database/department_management/department_management.sqlite"
    )
    failed_cand = {
        "id": "cand_1",
        "sql": "SELECT COUNT(*) / 12 FROM department",
        "type": "pruned",
        "confidence": 0.8
    }
    state.sql_candidates = [failed_cand]
    state.selected_candidate = failed_cand
    state.execution_results = [{"status": "success", "rows": 1, "data": [[0]], "error": None}]
    state.validation_result = ValidationResult(
        execution_success=False,
        errors=["Implicit integer division detected"]
    )
    
    msg = agent.act(state)
    assert msg is not None
    assert "repaired" in state.selected_candidate["type"]
    assert "CAST(COUNT(*) AS REAL)" in state.selected_candidate["sql"]
    assert len(state.repair_history) == 1
    assert state.repair_history[0]["strategy"] == "RULE_BASED"

# 5. LLM fallback flow via RepairAgent
def test_integration_llm_fallback_repair_agent(kb):
    mock_llm = MockLLMClient("SELECT head.born_state FROM department JOIN head ON department.Department_ID = head.head_ID")
    agent = RepairAgent(kb=kb)
    agent.llm_repairer._llm_client = mock_llm
    
    state = GraphState(
        original_request="Show born states of department heads",
        database="department_management",
        database_id="department_management",
        dialect="SQLite",
        db_path="spider_data/database/department_management/department_management.sqlite"
    )
    failed_cand = {
        "id": "cand_ambiguous",
        "sql": "SELECT born_state FROM department",
        "type": "pruned",
        "confidence": 0.8
    }
    state.sql_candidates = [failed_cand]
    state.selected_candidate = failed_cand
    state.execution_results = [{"status": "error", "error": "no such column: born_state"}]
    
    msg = agent.act(state)
    assert msg is not None
    assert len(state.repair_history) == 1

# 6. Multiple-error repair integration
def test_integration_multiple_error_repair(kb):
    engine = MapleDoctorEngine(kb=kb)
    # Query with two errors:
    # 1. DIVIDE function hallucination
    # 2. Schema typo 'Budget_in_Billion'
    sql = "SELECT DIVIDE(Budget_in_Billion, 5) FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such function: DIVIDE",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "DIVIDE" not in result.final_sql.upper()

# 7. Final validation integration
def test_integration_final_validation(kb):
    registry = setup_registry(kb=kb)
    assert registry.get_agent("RepairAgent") is not None
    assert registry.get_agent("ValidationExecutionAgent") is not None
    assert registry.get_agent("SQLGenerationAgent") is not None
    assert registry.get_agent("QueryUnderstandingAgent") is not None
    assert registry.get_agent("SchemaGroundingAgent") is not None
    assert registry.get_agent("RiskHedgingAgent") is not None

# 8. Failure/termination behavior integration
def test_integration_failure_termination_behavior(kb):
    mock_llm = MockLLMClient("INVALID REPAIR RESULT")
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)
    
    broken_sql = "INVALID SYNTAX AND LOGIC"
    result = engine.diagnose_and_repair(
        sql=broken_sql,
        error_text="syntax error near INVALID",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.final_sql == broken_sql
    assert result.termination_reason is not None
