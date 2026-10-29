from typing import Dict, List, Any, Optional
from src.models.state import ConceptGroundingResult, SchemaLinkingResult, ValidationResult

class SemanticVerifier:
    """
    Internal Semantic Verifier for ValidationExecutionAgent.
    Verifies that execution results align with user intent, schema mappings,
    and business concepts:
    - Expected columns vs returned columns
    - Aggregation consistency (e.g. if COUNT or SUM was requested, is scalar or aggregated column present?)
    - Suspicious empty results (0 rows when non-empty was expected)
    - Suspicious duplicate rows
    - Result shape and basic conceptual alignment
    """
    def verify(
        self,
        executed_sql: str,
        execution_dict: Dict[str, Any],
        concept_grounding: Optional[ConceptGroundingResult],
        schema_linking: Optional[SchemaLinkingResult]
    ) -> ValidationResult:
        """Evaluates semantic correctness of executed query result."""
        status = execution_dict.get("status", "error")
        errors = [execution_dict["error"]] if execution_dict.get("error") else []
        warnings: List[str] = []
        semantic_notes: List[str] = []
        
        row_count = execution_dict.get("rows", 0)
        columns = execution_dict.get("columns", [])
        data = execution_dict.get("data", [])

        if status != "success" or errors:
            return ValidationResult(
                execution_success=False,
                semantic_correctness=False,
                verification_status="failed",
                row_count=0,
                columns=[],
                rows=[],
                executed_sql=executed_sql,
                errors=errors,
                warnings=warnings,
                semantic_notes=["Execution resulted in database engine error"],
                confidence=0.0
            )

        # 1. Suspicious empty result check
        if row_count == 0:
            warnings.append("Suspicious empty result: Query returned 0 rows.")
            semantic_notes.append("Empty result set may indicate over-restrictive filter or incorrect join condition.")

        # 2. Aggregation consistency check
        if concept_grounding and concept_grounding.aggregations:
            has_agg_keyword = any(agg in executed_sql.upper() for agg in ["SUM(", "AVG(", "COUNT(", "MIN(", "MAX("])
            if not has_agg_keyword:
                warnings.append(f"Intent requested aggregation ({concept_grounding.aggregations}) but SQL lacks standard aggregation function")
                semantic_notes.append("Possible aggregation omission in SELECT clause.")

        # 3. Duplicate row check
        if len(data) > 1:
            try:
                row_tuples = [tuple(r) for r in data]
                if len(row_tuples) != len(set(row_tuples)):
                    warnings.append("Suspicious duplicate rows detected in execution result")
                    semantic_notes.append("Result contains duplicate rows; consider DISTINCT or proper GROUP BY")
            except Exception:
                pass

        # 4. Column alignment check
        if concept_grounding and concept_grounding.metrics:
            for metric in concept_grounding.metrics:
                found = any(metric.lower() in str(c).lower() for c in columns)
                if not found:
                    semantic_notes.append(f"Requested metric '{metric}' might not be clearly labeled in returned columns")

        semantic_correctness = len(errors) == 0 and (row_count > 0 or not warnings)
        verification_status = "passed" if semantic_correctness and not warnings else ("warning" if semantic_correctness else "failed")
        confidence = 0.95 if verification_status == "passed" else (0.80 if verification_status == "warning" else 0.4)

        return ValidationResult(
            execution_success=True,
            semantic_correctness=semantic_correctness,
            verification_status=verification_status,
            row_count=row_count,
            columns=columns,
            rows=data[:50],
            executed_sql=executed_sql,
            errors=errors,
            warnings=warnings,
            semantic_notes=semantic_notes,
            confidence=confidence
        )

