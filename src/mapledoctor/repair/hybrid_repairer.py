from typing import Optional, Tuple, Dict, Any
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, RepairStrategy
from src.mapledoctor.repair.rule_repairer import RuleRepairer
from src.mapledoctor.repair.llm_repairer import MapleDoctorLLMRepairer

class HybridRepairer:
    """
    Coordinates the Rule-First Hybrid Repair Strategy of MapleDoctor:
    1. Detect the error.
    2. If a high-confidence deterministic rule exists:
           APPLY THE RULE-BASED REPAIR.
    3. If the repair is ambiguous or semantic:
           INVOKE THE LLM REPAIRER with an error-specific constrained prompt.
    4. Validate and re-execute.
    """

    def __init__(
        self,
        kb: Optional[KnowledgeBase] = None,
        llm_client: Optional[Any] = None
    ):
        self.kb = kb
        self.rule_repairer = RuleRepairer(kb=kb)
        self.llm_repairer = MapleDoctorLLMRepairer(kb=kb, llm_client=llm_client)

    def repair(
        self,
        sql: str,
        detection: DetectionResult,
        question: str = "",
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite"
    ) -> Tuple[Optional[str], RepairStrategy, Optional[str], float]:
        """
        Executes the rule-first hybrid repair workflow.
        Returns:
            Tuple[repaired_sql, strategy_used, rule_or_method_name, confidence]
        """
        # Step 1: Rule-First Attempt
        if detection.is_rule_applicable:
            rule_sql, rule_name, rule_conf = self.rule_repairer.attempt_repair(
                sql=sql,
                detection=detection,
                dataset=dataset,
                database_id=database_id,
                dialect=dialect
            )
            if rule_sql and rule_conf >= 0.85:
                return rule_sql, RepairStrategy.RULE_BASED, rule_name, rule_conf

        # Step 2: Constrained LLM Fallback (Ambiguous, semantic, or no deterministic rule)
        llm_sql, llm_conf = self.llm_repairer.repair(
            question=question,
            failed_sql=sql,
            detection=detection,
            dataset=dataset,
            database_id=database_id,
            dialect=dialect
        )
        if llm_sql:
            method_desc = f"MapleDoctor_LLMRepair({detection.category.value})"
            return llm_sql, RepairStrategy.LLM_FALLBACK, method_desc, llm_conf

        return None, RepairStrategy.TERMINATE, "No viable repair found", 0.0
