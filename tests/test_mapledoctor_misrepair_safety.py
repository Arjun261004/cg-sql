import pytest
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.knowledge.core.repository import KnowledgeRepository
from src.mapledoctor.engine import MapleDoctorEngine
from src.mapledoctor.validator.repair_validator import RepairValidator
from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation

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
def validator(kb):
    return RepairValidator(kb=kb)

# 1. Extremum rewrite guard: MAX/MIN -> ORDER BY + LIMIT 1 is rejected by validator
def test_misrepair_guard_extremum_rewrite(validator):
    orig_sql = "SELECT MAX(Budget_in_Billions) FROM department"
    bad_repaired_sql = "SELECT Budget_in_Billions FROM department ORDER BY Budget_in_Billions DESC LIMIT 1"
    
    detection = DetectionResult(
        category=ErrorCategory.EMPTY_RESULT,
        description="Suspicious empty result",
        confidence=0.7
    )
    outcome = validator.validate_repair(
        original_sql=orig_sql,
        repaired_sql=bad_repaired_sql,
        original_detection=detection,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not outcome.is_valid
    assert any("Extremum rewrite" in v for v in outcome.safety_violations)

# 2. Projection drop guard: accidentally removing requested output columns
def test_misrepair_guard_projection_drop(validator):
    orig_sql = "SELECT Department_ID, Name, Creation, Ranking FROM department"
    bad_repaired_sql = "SELECT Name FROM department"
    
    outcome = validator.validate_repair(
        original_sql=orig_sql,
        repaired_sql=bad_repaired_sql,
        original_detection=None,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not outcome.is_valid
    assert any("Projection drop" in v for v in outcome.safety_violations)

# 3. Schema/column hallucination guard: introducing non-existent columns/tables
def test_misrepair_guard_schema_hallucination(validator):
    orig_sql = "SELECT Name FROM department"
    bad_repaired_sql = "SELECT Name FROM hallucinated_fake_table"
    
    outcome = validator.validate_repair(
        original_sql=orig_sql,
        repaired_sql=bad_repaired_sql,
        original_detection=None,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not outcome.is_valid
    assert any("Schema hallucination" in v for v in outcome.safety_violations)

# 4. CAST injection guard: unnecessary CAST on text-like values without evidence
def test_misrepair_guard_cast_injection(kb):
    engine = MapleDoctorEngine(kb=kb)
    # Valid text column 'born_state' in head table
    sql = "SELECT born_state FROM head WHERE born_state = 'California'"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert "CAST(" not in res.final_sql

# 5. Value over-correction guard: replacing a correct constant with recommended value
def test_misrepair_guard_value_overcorrection(kb):
    engine = MapleDoctorEngine(kb=kb)
    sql = "SELECT * FROM department WHERE Creation = '1789'"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert "1789" in res.final_sql

# 6. Value over-correction from empty/NULL symptoms guard
def test_misrepair_guard_empty_symptom_overcorrection(kb):
    mock_llm = MockLLMClient("SELECT * FROM department WHERE Ranking > 50")
    engine = MapleDoctorEngine(kb=kb, llm_client=mock_llm)
    sql = "SELECT * FROM department WHERE Ranking > 50"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    # Stays unchanged if already sound
    assert res.final_sql == sql

# 7. Column substitution guard: replacing a correct column with wrong-but-existing column
def test_misrepair_guard_column_substitution(kb):
    engine = MapleDoctorEngine(kb=kb)
    sql = "SELECT Num_Employees FROM department WHERE Ranking = 1"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert "Num_Employees" in res.final_sql

# 8. Predicate flip/contradiction guard: breaking negation or set logic
def test_misrepair_guard_predicate_flip(kb):
    engine = MapleDoctorEngine(kb=kb)
    sql = "SELECT Name FROM department WHERE Ranking NOT IN (1, 2, 3)"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert "NOT IN" in res.final_sql

# 9. Rule-based over-triggering guard: deterministic rewrite changing valid SQL semantics
def test_misrepair_guard_rule_overtriggering(kb):
    engine = MapleDoctorEngine(kb=kb)
    # Valid = comparison against integer should not trigger = -> IN
    sql = "SELECT Name FROM department WHERE Department_ID = 1"
    res = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert not res.was_repaired
    assert "Department_ID = 1" in res.final_sql
