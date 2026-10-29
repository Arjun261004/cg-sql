import pytest
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.knowledge.core.repository import KnowledgeRepository
from src.mapledoctor.engine import MapleDoctorEngine

@pytest.fixture
def kb():
    repo = KnowledgeRepository()
    return KnowledgeBase(repo)

@pytest.fixture
def engine(kb):
    return MapleDoctorEngine(kb=kb)

# 1. Valid JOINs without explicit FK metadata (not falsely flagged if probe shows overlapping data)
def test_valid_join_without_fk_metadata(engine):
    sql = "SELECT department.Name FROM department JOIN management ON department.Department_ID = management.department_ID"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql

class MockLLMClient:
    def __init__(self, fixed_response: str = ""):
        self.fixed_response = fixed_response

    def generate_text(self, prompt: str) -> str:
        return self.fixed_response

# 2. Legitimate empty-result queries (not corrupted)
def test_legitimate_empty_result_query(kb):
    sql = "SELECT Name FROM department WHERE Budget_in_Billions > 9999999"
    # When legitimate empty result is returned, conservative LLM decides not to rewrite
    mock_llm = MockLLMClient(sql)
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)
    res = engine.diagnose_and_repair(
        sql=sql,
        question="Find departments with impossible budget > 9999999",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql
    assert res.is_executable

# 3. Legitimate NULL-result queries (e.g. MIN on empty or NULL table without crash)
def test_legitimate_null_result_query(kb):
    sql = "SELECT MIN(Creation) FROM department WHERE Ranking < 0"
    mock_llm = MockLLMClient(sql)
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)
    res = engine.diagnose_and_repair(
        sql=sql,
        question="What is minimum creation for negative ranking?",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql
    assert res.is_executable

# 4. Valid "=" comparisons (not converted to IN when RHS is single scalar value)
def test_valid_equals_comparison(engine):
    sql = "SELECT Name FROM department WHERE Ranking = 1"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert "Ranking = 1" in res.final_sql
    assert "IN" not in res.final_sql

# 5. Valid MIN/MAX operations (already having NOT NULL or on non-null column)
def test_valid_min_max_operation(engine):
    sql = "SELECT MAX(Budget_in_Billions) FROM department WHERE Budget_in_Billions IS NOT NULL"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql

# 6. Valid CAST operations (already cast, not double cast)
def test_valid_cast_operation(engine):
    sql = "SELECT CAST(COUNT(*) AS REAL) / 12 FROM department"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql

# 7. Valid aliases (alias defined and consistently used)
def test_valid_aliases(engine):
    sql = "SELECT D.Name, D.Ranking FROM department AS D WHERE D.Ranking > 1"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql

# 8. Valid table and column references
def test_valid_table_and_column_references(engine):
    sql = "SELECT Department_ID, Name, Creation, Ranking, Budget_in_Billions, Num_Employees FROM department"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql

# 9. Valid enumeration values (exact case match)
def test_valid_enumeration_values(engine):
    sql = "SELECT * FROM management WHERE temporary_acting = 'Yes'"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert "temporary_acting = 'Yes'" in res.final_sql

# 10. Valid text comparisons (LIKE pattern or exact string)
def test_valid_text_comparisons(engine):
    sql = "SELECT * FROM department WHERE Name LIKE '%State%'"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql

# 11. Valid aggregate operations (standard COUNT, SUM, AVG on numeric)
def test_valid_aggregate_operations(engine):
    sql = "SELECT COUNT(*), AVG(Budget_in_Billions) FROM department"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert res.final_sql == sql
