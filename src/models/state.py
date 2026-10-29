from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from src.models.messages import AgentMessage

class ConceptGroundingResult(BaseModel):
    """Output produced by QueryUnderstandingAgent."""
    original_query: str = ""
    normalized_query: str = ""
    entities: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    filters: List[Dict[str, Any]] = Field(default_factory=list)
    temporal_constraints: List[str] = Field(default_factory=list)
    aggregations: List[str] = Field(default_factory=list)
    sorting_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    limits: Optional[int] = None
    comparison_requirements: List[str] = Field(default_factory=list)
    user_confirmed_mappings: Dict[str, Any] = Field(default_factory=dict)
    ambiguous_terms: List[str] = Field(default_factory=list)
    business_terms: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    unresolved_concepts: List[str] = Field(default_factory=list)

class SchemaLinkingResult(BaseModel):
    """Output produced by SchemaGroundingAgent."""
    final_tables: List[str] = Field(default_factory=list)
    final_columns: Dict[str, List[str]] = Field(default_factory=dict)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    join_paths: List[List[Dict[str, Any]]] = Field(default_factory=list)
    concept_mappings: Dict[str, str] = Field(default_factory=dict)
    unmatched_concepts: List[str] = Field(default_factory=list)
    ambiguous_mappings: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    provenance: Dict[str, Any] = Field(default_factory=dict)
    full_schema_candidate: Dict[str, Any] = Field(default_factory=dict)
    pruned_schema_candidate: Dict[str, Any] = Field(default_factory=dict)

class ValidationResult(BaseModel):
    """Output produced by ValidationExecutionAgent."""
    execution_success: bool = False
    semantic_correctness: bool = False
    verification_status: str = "unverified"  # "passed", "failed", "warning"
    row_count: int = 0
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    executed_sql: str = ""
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    semantic_notes: List[str] = Field(default_factory=list)
    confidence: float = 0.0

class RiskEvaluation(BaseModel):
    """Output produced by RiskHedgingAgent."""
    candidate_evaluations: List[Dict[str, Any]] = Field(default_factory=list)
    selected_candidate_id: str = ""
    selected_candidate_type: str = ""  # "full" vs "pruned"
    hedging_strategy: str = "confidence_and_simplicity"
    risk_factors: List[str] = Field(default_factory=list)
    decision_rationale: str = ""
    confidence: float = 0.0

class GraphState(BaseModel):
    """
    Shared Blackboard State across all six intelligent agents.
    Maintains grounded facts, intermediate evidence, candidates, and execution results.
    """
    # Core inputs
    original_request: str = ""
    query: str = ""  # Normalized / reference query
    intent: str = ""
    database: str = "default"
    database_id: str = ""
    dataset: str = "spider"
    db_path: str = ""  # Full path to database file (e.g. SQLite)
    dialect: str = "SQLite"

    # Grounding results from QueryUnderstandingAgent & SchemaGroundingAgent
    concept_grounding: Optional[ConceptGroundingResult] = None
    schema_linking: Optional[SchemaLinkingResult] = None
    conceptual_model: Dict[str, Any] = Field(default_factory=dict)
    schema_context: Dict[str, Any] = Field(default_factory=dict)
    schema_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    enterprise_context: Dict[str, Any] = Field(default_factory=dict)
    er_context: Dict[str, Any] = Field(default_factory=dict)
    dialect_context: Dict[str, Any] = Field(default_factory=dict)

    # Knowledge Base evidence
    knowledge_context: Dict[str, Any] = Field(default_factory=dict)
    knowledge_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    schema_linking_hypothesis: Dict[str, Any] = Field(default_factory=dict)
    knowledge_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    knowledge_queries: List[Dict[str, Any]] = Field(default_factory=list)

    # Query Planning and SQL Candidate Generation
    query_plans: List[Dict[str, Any]] = Field(default_factory=list)
    sql_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    selected_candidate: Optional[Dict[str, Any]] = None

    # Validation, Execution, and Repair
    validation_result: Optional[ValidationResult] = None
    execution_results: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)
    repair_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    repair_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Risk Hedging
    risk_evaluation: Optional[RiskEvaluation] = None

    # History and Coordination
    decision_history: List[Dict[str, Any]] = Field(default_factory=list)
    execution_history: List[Dict[str, Any]] = Field(default_factory=list)
    agent_messages: List[AgentMessage] = Field(default_factory=list)
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    requested_next_agent: Optional[str] = None

    # Final Output
    final_answer: str = ""
    final_sql: str = ""
    final_confidence: float = 0.0

    # Runtime metadata
    metrics: Dict[str, Any] = Field(default_factory=dict)
    trace: List[str] = Field(default_factory=list)
    iteration_count: int = 0
    max_iterations: int = 20
    is_terminated: bool = False
    mapledoctor_verified: bool = False

    def add_message(self, message: AgentMessage):
        self.agent_messages.append(message)
        self.trace.append(str(message))
