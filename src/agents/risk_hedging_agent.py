import re
from typing import Dict, List, Any, Optional
from src.agents.base_agent import BaseAgent
from src.models.state import GraphState, RiskEvaluation
from src.models.messages import AgentMessage, MessageType
from src.core.agent_registry import AgentDescriptor

class RiskHedgingAgent(BaseAgent):
    """
    AGENT 6 — RiskHedgingAgent
    Role: Risk-hedged SQL candidate selection and evidence evaluation.
    Compares alternative SQL candidates (e.g. Candidate A full-schema vs Candidate B pruned-schema,
    or repaired candidates) based on multidimensional evidence:
    - execution success
    - semantic verification
    - schema grounding simplicity
    - duplicate row risk
    - unnecessary joins penalty
    - result non-emptiness
    """
    def __init__(self, kb=None):
        super().__init__("RiskHedgingAgent", "Risk-hedged SQL candidate selection and evidence evaluation", kb=kb)

    def get_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            name=self.name,
            role=self.role,
            capabilities=[
                "candidate_comparison",
                "risk_scoring",
                "unnecessary_join_detection",
                "hedging_decision"
            ],
            tools=["risk_evaluator"],
            input_requirements=["sql_candidates", "validation_result"],
            activation_conditions=["candidates_evaluated"]
        )

    def observe(self, state: GraphState) -> None:
        pass

    def reason(self, state: GraphState) -> None:
        pass

    def evaluate_evidence(self, state: GraphState) -> float:
        if state.risk_evaluation:
            return state.risk_evaluation.confidence
        return 0.90

    def _score_candidate(self, candidate: Dict[str, Any], state: GraphState) -> Dict[str, Any]:
        """Calculates evidence-based score for a SQL candidate."""
        score = 0.0
        factors = []
        sql = candidate.get("sql", "")
        cand_type = candidate.get("type", "unknown")

        # 1. Execution Success
        val = candidate.get("validation", {})
        if not val and state.validation_result and state.selected_candidate == candidate:
            val = state.validation_result.dict()

        exec_success = val.get("execution_success", False) if val else False
        if exec_success:
            score += 0.50
            factors.append("+0.50 Execution succeeded")
        else:
            factors.append("-0.50 Execution failed or not run")

        # 2. Semantic Verification Status
        status = val.get("verification_status", "unverified") if val else "unverified"
        if status == "passed":
            score += 0.30
            factors.append("+0.30 Semantic verification passed")
        elif status == "warning":
            score += 0.15
            factors.append("+0.15 Semantic verification has warnings")

        # 3. Schema Simplicity: Pruned Context Preference
        if cand_type == "pruned":
            score += 0.10
            factors.append("+0.10 Pruned minimal schema (lower surface area)")

        # 4. Unnecessary Joins Penalty
        join_count = len(re.findall(r'\bJOIN\b', sql, re.IGNORECASE))
        if join_count > 2:
            score -= 0.15
            factors.append(f"-0.15 High join count ({join_count}) carries extra risk")

        # 5. Duplicate Row Risk Penalty
        if val and any("duplicate rows" in w.lower() for w in val.get("warnings", [])):
            score -= 0.20
            factors.append("-0.20 Duplicate rows detected in result")

        # 6. Non-empty Result Reward
        if val and val.get("row_count", 0) > 0:
            score += 0.10
            factors.append("+0.10 Non-empty result set returned")

        confidence = max(0.1, min(1.0, score))
        return {
            "id": candidate.get("id", "unknown"),
            "type": cand_type,
            "sql": sql,
            "score": round(score, 3),
            "confidence": round(confidence, 3),
            "factors": factors
        }

    def propose_action(self, state: GraphState) -> Optional[AgentMessage]:
        if state.final_sql and state.risk_evaluation:
            return None

        if not state.sql_candidates:
            return None

        evaluations = [self._score_candidate(c, state) for c in state.sql_candidates]

        # Select highest-scoring candidate
        best_eval = max(evaluations, key=lambda x: x["score"])
        selected_cand = next(c for c in state.sql_candidates if c.get("id") == best_eval["id"])

        rationale = (
            f"Selected {best_eval['type']} candidate ({best_eval['id']}) with score {best_eval['score']}. "
            f"Key factors: {'; '.join(best_eval['factors'])}"
        )

        risk_eval = RiskEvaluation(
            candidate_evaluations=evaluations,
            selected_candidate_id=best_eval["id"],
            selected_candidate_type=best_eval["type"],
            hedging_strategy="evidence_confidence_and_simplicity",
            risk_factors=best_eval["factors"],
            decision_rationale=rationale,
            confidence=best_eval["confidence"]
        )

        state.risk_evaluation = risk_eval
        state.selected_candidate = selected_cand
        state.final_sql = selected_cand.get("sql", "")
        state.final_confidence = best_eval["confidence"]

        val = selected_cand.get("validation", {})
        if not val and state.validation_result:
            val = state.validation_result.dict()

        if val and val.get("execution_success"):
            state.final_answer = f"Validated SQL successfully ({val.get('row_count', 0)} rows returned)."
        elif state.final_answer and "Schema Error" in state.final_answer:
            state.final_confidence = 0.0
        else:
            error_reason = "; ".join(val.get("errors", [])) if val else ""
            if not error_reason and state.validation_result:
                error_reason = "; ".join(state.validation_result.errors)
            state.final_answer = f"Execution Failure: {error_reason or 'Query execution failed or schema attributes do not exist.'}"
            state.final_confidence = 0.0

        return AgentMessage(
            agent=self.name,
            message_type=MessageType.DECISION,
            capability="Risk Hedging & Candidate Selection",
            claim=f"DECISION: {rationale}",
            evidence=[risk_eval.dict()],
            confidence=best_eval["confidence"]
        )
