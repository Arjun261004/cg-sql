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

@pytest.fixture
def engine(kb):
    return MapleDoctorEngine(kb=kb)

# ============================================================
# TEST 01: Function Hallucination (Rule 1)
# ============================================================
def test_01_function_hallucination_divide(engine):
    sql = "SELECT DIVIDE(Num_Employees, 10) FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such function: DIVIDE",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "DIVIDE" not in result.final_sql.upper()
    assert "/" in result.final_sql
    assert result.repair_history[0].category == ErrorCategory.FUNCTION_HALLUCINATION
    assert result.repair_history[0].strategy == RepairStrategy.RULE_BASED

def test_01_function_hallucination_year(engine):
    sql = "SELECT YEAR(Creation) FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such function: YEAR",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "strftime('%Y'" in result.final_sql or 'strftime' in result.final_sql
    assert result.repair_history[0].category == ErrorCategory.FUNCTION_HALLUCINATION

def test_01_function_hallucination_date_trunc(engine):
    sql = "SELECT DATE_TRUNC('year', Creation) FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such function: DATE_TRUNC",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "strftime('%Y'" in result.final_sql

# ============================================================
# TEST 02: Table-Column Mismatch (Rule 2)
# ============================================================
def test_02_table_column_mismatch_single_table(engine):
    # In department_management, 'born_state' exists in table 'head', not 'department'
    sql = "SELECT department.born_state FROM department JOIN head ON department.Department_ID = head.head_ID"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such column: department.born_state",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "head.born_state" in result.final_sql
    assert result.repair_history[0].category == ErrorCategory.TABLE_COLUMN_MISMATCH
    assert result.repair_history[0].strategy == RepairStrategy.RULE_BASED

# ============================================================
# TEST 03: Unused Alias (Rule 3)
# ============================================================
def test_03_unused_alias(engine):
    sql = "SELECT department.Name FROM department AS D WHERE department.Ranking > 2"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such column: department.Name",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "D.Name" in result.final_sql
    assert result.repair_history[0].category == ErrorCategory.UNUSED_ALIAS
    assert result.repair_history[0].strategy == RepairStrategy.RULE_BASED

# ============================================================
# TEST 04: Schema Hallucination (Rule 4)
# ============================================================
def test_04_schema_hallucination_edit_distance(engine):
    # Typo: 'Budget_in_Billion' instead of 'Budget_in_Billions'
    sql = "SELECT Budget_in_Billion FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such column: Budget_in_Billion",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "Budget_in_Billions" in result.final_sql
    assert result.repair_history[0].category == ErrorCategory.SCHEMA_HALLUCINATION
    assert result.repair_history[0].strategy == RepairStrategy.RULE_BASED

# ============================================================
# TEST 05: Missing JOIN (Rule 5)
# ============================================================
def test_05_missing_join_single_fk(engine):
    # 'temporary_acting' is in 'management'. Foreign key exists: management.department_ID = department.Department_ID
    sql = "SELECT department.Name, temporary_acting FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="no such column: temporary_acting",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "JOIN MANAGEMENT" in result.final_sql.upper()
    assert result.repair_history[0].category == ErrorCategory.MISSING_JOIN
    assert result.repair_history[0].strategy == RepairStrategy.RULE_BASED

# ============================================================
# TEST 06: Implicit Type Conversion (Rule 6)
# ============================================================
def test_06_implicit_type_conversion(engine):
    sql = "SELECT COUNT(*) / 12 FROM department"
    result = engine.diagnose_and_repair(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "CAST(COUNT(*) AS REAL)" in result.final_sql
    assert result.repair_history[0].category == ErrorCategory.IMPLICIT_TYPE_CONVERSION
    assert result.repair_history[0].strategy == RepairStrategy.RULE_BASED

# ============================================================
# TEST 07: Using "=" instead of "IN" (Rule 7)
# ============================================================
def test_07_equals_instead_of_in(engine):
    sql = "SELECT Name FROM department WHERE Department_ID = (SELECT department_ID FROM management)"
    result = engine.diagnose_and_repair(
        sql=sql,
        error_text="more than one row returned by a subquery used as an expression",
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert result.was_repaired
    assert "IN (" in result.final_sql
    assert result.repair_history[0].category == ErrorCategory.EQUALS_INSTEAD_OF_IN
    assert result.repair_history[0].strategy == RepairStrategy.RULE_BASED

# ============================================================
# TEST 08: Ascending Sort with NULL (Rule 8)
# ============================================================
def test_08_ascending_sort_with_null(engine):
    # MIN(Num_Employees) without NULL filter
    sql = "SELECT MIN(Num_Employees) FROM department"
    detection = engine.detector.detect(
        sql=sql,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    # Force probe simulation for nullable column
    from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
    forced_detection = DetectionResult(
        category=ErrorCategory.ASCENDING_SORT_WITH_NULL,
        description="MIN(Num_Employees) on nullable column without IS NOT NULL",
        location=ErrorLocation(clause="SELECT", column="Num_Employees"),
        confidence=0.92,
        rule_name="MapleDoctor_Rule8_AscendingSortWithNull",
        is_rule_applicable=True,
        evidence={"column": "Num_Employees"}
    )
    repaired, rule_name, conf = engine.repairer.rule_repairer.attempt_repair(
        sql=sql,
        detection=forced_detection,
        dataset="spider",
        database_id="department_management",
        dialect="SQLite"
    )
    assert repaired is not None
    assert "Num_Employees IS NOT NULL" in repaired

# ============================================================
# TEST 09: Comparing Unrelated Columns (Rule 9)
# ============================================================
def test_09_comparing_unrelated_columns(engine):
    # cards.id = sets.id -> replaced with valid FK
    from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
    detection = DetectionResult(
        category=ErrorCategory.COMPARING_UNRELATED_COLUMNS,
        description="JOIN condition compares unrelated columns",
        location=ErrorLocation(clause="JOIN", predicate="cards.id = sets.id"),
        confidence=0.95,
        rule_name="MapleDoctor_Rule9_ComparingUnrelatedColumns",
        is_rule_applicable=True,
        evidence={
            "candidate_fks": [{
                "source_table": "cards",
                "source_column": "setCode",
                "target_table": "sets",
                "target_column": "code"
            }]
        }
    )
    sql = "SELECT cards.name FROM cards JOIN sets ON cards.id = sets.id"
    repaired, rule_name, conf = engine.repairer.rule_repairer.attempt_repair(
        sql=sql,
        detection=detection,
        dataset="spider",
        database_id="default",
        dialect="SQLite"
    )
    assert repaired is not None
    assert "cards.setCode = sets.code" in repaired

# ============================================================
# TEST 10: Violating Value Specification (Rule 10 - LLM Fallback)
# ============================================================
def test_10_violating_value_specification(kb):
    mock_llm = MockLLMClient("SELECT * FROM cards WHERE status = 'Legal'")
    engine_mock = MapleDoctorEngine(kb=kb, llm_client=mock_llm)
    
    from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
    detection = DetectionResult(
        category=ErrorCategory.VIOLATING_VALUE_SPECIFICATION,
        description="Value 'legal' violates column specification. Matching: 'Legal'",
        location=ErrorLocation(clause="WHERE", column="status"),
        confidence=0.90,
        is_rule_applicable=False,
        evidence={"target_value": "legal", "valid_values": ["Legal", "Banned", "Restricted"]}
    )
    repaired, strategy, rule_name, conf = engine_mock.repairer.repair(
        sql="SELECT * FROM cards WHERE status = 'legal'",
        detection=detection,
        question="Find cards that are legal",
        dataset="spider",
        database_id="default",
        dialect="SQLite"
    )
    assert repaired == "SELECT * FROM cards WHERE status = 'Legal'"
    assert strategy == RepairStrategy.LLM_FALLBACK
    assert "Legal" in mock_llm.last_prompt

# ============================================================
# TEST 11: Aggregation / Comparison Misuse (Rule 11 - LLM Fallback)
# ============================================================
def test_11_aggregation_comparison_misuse(kb):
    mock_llm = MockLLMClient("SELECT MAX(CAST(speed AS REAL)) FROM cars")
    engine_mock = MapleDoctorEngine(kb=kb, llm_client=mock_llm)
    
    from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
    detection = DetectionResult(
        category=ErrorCategory.AGGREGATION_COMPARISON_MISUSE,
        description="MAX() on TEXT column 'speed' containing numeric values causes lexicographical sorting",
        location=ErrorLocation(clause="SELECT", column="speed", function="MAX"),
        confidence=0.88,
        is_rule_applicable=False,
        evidence={"column": "speed", "sample_values": ["10", "25", "100"]}
    )
    repaired, strategy, rule_name, conf = engine_mock.repairer.repair(
        sql="SELECT MAX(speed) FROM cars",
        detection=detection,
        question="What is the maximum speed?",
        dataset="spider",
        database_id="default",
        dialect="SQLite"
    )
    assert repaired == "SELECT MAX(CAST(speed AS REAL)) FROM cars"
    assert strategy == RepairStrategy.LLM_FALLBACK
