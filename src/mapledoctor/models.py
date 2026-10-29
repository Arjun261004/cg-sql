from enum import Enum
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class ErrorCategory(str, Enum):
    # Rule 1 to 11
    FUNCTION_HALLUCINATION = "FUNCTION_HALLUCINATION"
    TABLE_COLUMN_MISMATCH = "TABLE_COLUMN_MISMATCH"
    UNUSED_ALIAS = "UNUSED_ALIAS"
    SCHEMA_HALLUCINATION = "SCHEMA_HALLUCINATION"
    MISSING_JOIN = "MISSING_JOIN"
    IMPLICIT_TYPE_CONVERSION = "IMPLICIT_TYPE_CONVERSION"
    EQUALS_INSTEAD_OF_IN = "EQUALS_INSTEAD_OF_IN"
    ASCENDING_SORT_WITH_NULL = "ASCENDING_SORT_WITH_NULL"
    COMPARING_UNRELATED_COLUMNS = "COMPARING_UNRELATED_COLUMNS"
    VIOLATING_VALUE_SPECIFICATION = "VIOLATING_VALUE_SPECIFICATION"
    AGGREGATION_COMPARISON_MISUSE = "AGGREGATION_COMPARISON_MISUSE"

    # Suspicious execution symptoms
    EMPTY_RESULT = "EMPTY_RESULT"
    SINGLE_NULL_RESULT = "SINGLE_NULL_RESULT"

    # Syntax and fallback categories
    SYNTAX_ERROR = "SYNTAX_ERROR"
    DBMS_EXECUTION_ERROR = "DBMS_EXECUTION_ERROR"
    UNKNOWN = "UNKNOWN"

class ErrorLocation(BaseModel):
    clause: Optional[str] = None          # SELECT, FROM, WHERE, JOIN, ORDER BY, GROUP BY
    table: Optional[str] = None
    column: Optional[str] = None
    operator: Optional[str] = None        # =, /, IN, <, >
    function: Optional[str] = None        # DIVIDE, YEAR, MIN, etc.
    join_target: Optional[str] = None
    predicate: Optional[str] = None
    ast_path: Optional[str] = None

class DetectionResult(BaseModel):
    category: ErrorCategory
    description: str
    location: ErrorLocation = Field(default_factory=ErrorLocation)
    confidence: float = 0.0
    rule_name: Optional[str] = None
    is_rule_applicable: bool = False
    evidence: Dict[str, Any] = Field(default_factory=dict)
    probe_result: Optional[Dict[str, Any]] = None
    raw_error: Optional[str] = None

class RepairStrategy(str, Enum):
    RULE_BASED = "RULE_BASED"
    LLM_FALLBACK = "LLM_FALLBACK"
    TERMINATE = "TERMINATE"
    NO_REPAIR_NEEDED = "NO_REPAIR_NEEDED"

class RepairAttempt(BaseModel):
    iteration: int
    category: ErrorCategory
    strategy: RepairStrategy
    rule_name: Optional[str] = None
    original_sql: str
    repaired_sql: str
    confidence: float
    explanation: str = ""
    re_execution_result: Optional[Dict[str, Any]] = None
    success: bool = False
    remaining_error: Optional[str] = None

class MapleDoctorResult(BaseModel):
    original_sql: str
    final_sql: str
    was_repaired: bool = False
    error_detected: bool = False
    initial_detection: Optional[DetectionResult] = None
    iterations: int = 0
    repair_history: List[RepairAttempt] = Field(default_factory=list)
    is_executable: bool = True
    final_execution_data: Optional[Dict[str, Any]] = None
    trace: List[str] = Field(default_factory=list)
    termination_reason: Optional[str] = None
