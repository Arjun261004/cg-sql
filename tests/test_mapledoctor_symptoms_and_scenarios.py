import pytest
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.knowledge.core.repository import KnowledgeRepository
from src.mapledoctor.engine import MapleDoctorEngine
from src.mapledoctor.models import ErrorCategory, RepairStrategy

class MockLLMClient:
    def __init__(self, fixed_response: str = ""):
        self.fixed_response = fixed_response
        self.last_prompt = ""

    def generate_text(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.fixed_response

@pytest.fixture
def kb():
    repo = KnowledgeRepository()
    return KnowledgeBase(repo)

# ============================================================
# TEST 12: Empty-Result Suspicious Symptom
# ============================================================
def test_12_empty_result_symptom(kb):
    mock_llm = MockLLMClient("SELECT * FROM department WHERE Ranking >= 1")
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)
    
    # Query executed successfully but returned 0 rows
    exec_dict = {
        "status": "success",
        "rows": 0,
        "columns": ["Department_ID", "Name"],
        "data": [],
        "error": None
    }
    sql = "SELECT * FROM department WHERE Ranking > 99999"
    result = engine.diagnose_and_repair(
        sql=sql,
        question="Find all departments with ranking over 99999",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite",
        execution_dict=exec_dict
    )
    assert result.error_detected
    assert result.initial_detection.category == ErrorCategory.EMPTY_RESULT
    assert "EMPTY_RESULT" in mock_llm.last_prompt

# ============================================================
# TEST 13: NULL-Result Suspicious Symptom
# ============================================================
def test_13_null_result_symptom(kb):
    mock_llm = MockLLMClient("SELECT MAX(Ranking) FROM department")
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)
    
    # Query returned single NULL row
    exec_dict = {
        "status": "success",
        "rows": 1,
        "columns": ["max_budget"],
        "data": [[None]],
        "error": None
    }
    sql = "SELECT MAX(Budget_in_Billions) FROM department WHERE Ranking > 9999"
    result = engine.diagnose_and_repair(
        sql=sql,
        question="What is the maximum budget?",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite",
        execution_dict=exec_dict
    )
    assert result.error_detected
    assert result.initial_detection.category == ErrorCategory.SINGLE_NULL_RESULT
    assert "SINGLE_NULL_RESULT" in mock_llm.last_prompt

# ============================================================
# TEST 14: Multiple Simultaneous Errors (Iterative Multi-Error Repair)
# ============================================================
def test_14_multiple_simultaneous_errors(kb):
    engine = MapleDoctorEngine(kb=kb)
    # Query contains:
    # 1. Function hallucination: DIVIDE(x, y)
    # 2. Schema Hallucination typo: Budget_in_Billion instead of Budget_in_Billions
    sql = "SELECT DIVIDE(Budget_in_Billion, 10) FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such function: DIVIDE",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    # Function hallucination repaired
    assert "DIVIDE" not in result.final_sql.upper()
    assert "/" in result.final_sql

# ============================================================
# TEST 15: Ambiguous Repair Requiring LLM Fallback
# ============================================================
def test_15_ambiguous_repair_llm_fallback(kb):
    mock_llm = MockLLMClient("SELECT department.Name, management.temporary_acting FROM department JOIN management ON department.Department_ID = management.department_ID")
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)

    from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
    # Ambiguous: column exists in multiple tables
    detection = DetectionResult(
        category=ErrorCategory.TABLE_COLUMN_MISMATCH,
        description="Column 'id' exists in multiple tables: ['department', 'head', 'management']",
        location=ErrorLocation(clause="SELECT", column="id"),
        confidence=0.70,
        is_rule_applicable=False, # Multiple candidates -> LLM fallback
        evidence={"matching_tables": ["department", "head", "management"], "column": "id"}
    )
    repaired, strategy, rule_name, conf = engine.repairer.repair(
        sql="SELECT id FROM department",
        detection=detection,
        question="Show department IDs",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert strategy == RepairStrategy.LLM_FALLBACK
    assert "department" in mock_llm.last_prompt
    assert "head" in mock_llm.last_prompt

# ============================================================
# TEST 16: Correct SQL That Must NOT Be Modified
# ============================================================
def test_16_correct_sql_untouched(kb):
    engine = MapleDoctorEngine(kb=kb)
    sql = "SELECT Name, Creation FROM department WHERE Ranking > 2 ORDER BY Creation DESC"
    result = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not result.error_detected
    assert not result.was_repaired
    assert result.final_sql == sql
    assert result.iterations == 0

# ============================================================
# TEST 17: SQL with Valid Foreign-Key JOIN
# ============================================================
def test_17_valid_foreign_key_join(kb):
    engine = MapleDoctorEngine(kb=kb)
    # Valid JOIN between department and management on foreign key
    sql = "SELECT department.Name, management.temporary_acting FROM department JOIN management ON department.Department_ID = management.department_ID"
    result = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not result.error_detected
    assert not result.was_repaired
    assert result.final_sql == sql

# ============================================================
# TEST 18: SQL with Multiple Foreign-Key Candidates (Ambiguous)
# ============================================================
def test_18_multiple_fk_candidates_fallback(kb):
    mock_llm = MockLLMClient("SELECT * FROM table_a JOIN table_b ON table_a.fk1 = table_b.id")
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)

    from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
    detection = DetectionResult(
        category=ErrorCategory.COMPARING_UNRELATED_COLUMNS,
        description="JOIN condition compares unrelated columns; multiple FK candidates exist",
        location=ErrorLocation(clause="JOIN", predicate="table_a.x = table_b.y"),
        confidence=0.70,
        is_rule_applicable=False, # Multiple FK candidates -> LLM fallback
        evidence={
            "candidate_fks": [
                {"source_table": "table_a", "source_column": "fk1", "target_table": "table_b", "target_column": "id"},
                {"source_table": "table_a", "source_column": "fk2", "target_table": "table_b", "target_column": "id"}
            ]
        }
    )
    repaired, strategy, rule_name, conf = engine.repairer.repair(
        sql="SELECT * FROM table_a JOIN table_b ON table_a.x = table_b.y",
        detection=detection,
        question="Join table a and table b",
        dataset="spider",
        database_id="default",
        dialect="SQLite"
    )
    assert strategy == RepairStrategy.LLM_FALLBACK
    assert "fk1" in mock_llm.last_prompt
    assert "fk2" in mock_llm.last_prompt

# ============================================================
# TEST 19: Non-Existent Schema Element with No Valid Correction
# ============================================================
def test_19_non_existent_schema_no_correction(kb):
    mock_llm = MockLLMClient("SELECT Name FROM department")
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)

    # Completely alien column name with no edit distance match
    sql = "SELECT zzz_completely_nonexistent_col_xxx FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such column: zzz_completely_nonexistent_col_xxx",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    # The rule repairer cannot deterministically repair because edit distance has no match
    # It must fallback to LLM
    assert result.error_detected
    assert result.initial_detection.category == ErrorCategory.SCHEMA_HALLUCINATION
    assert result.initial_detection.is_rule_applicable == False

# ============================================================
# TEST 20: Query That Remains Non-Executable After Attempted Repair
# ============================================================
def test_20_non_executable_termination_behavior(kb):
    # LLM returns invalid garbage that cannot execute
    mock_llm = MockLLMClient("TOTALLY INVALID SQL SYNTAX @@@")
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)

    broken_sql = "SELECT FROM WHERE"
    result = engine.diagnose_and_repair(
        sql=broken_sql,
        error_text="syntax error near FROM",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    # Per paper protocol: If query remains non-executable after repair attempts,
    # terminate and return the original query!
    assert result.final_sql == broken_sql
    assert result.termination_reason is not None
    assert "reverted to original query" in result.termination_reason.lower()
