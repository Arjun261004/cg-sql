from typing import Optional, Tuple, List, Dict
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.rules import (
    MapleRule,
    FunctionHallucinationRule,
    TableColumnMismatchRule,
    UnusedAliasRule,
    SchemaHallucinationRule,
    MissingJoinRule,
    ImplicitTypeConversionRule,
    EqualsInsteadOfInRule,
    AscendingSortWithNullRule,
    ComparingUnrelatedColumnsRule,
    ViolatingValueSpecificationRule,
    AggregationComparisonMisuseRule,
    SuspiciousSymptomsRule
)

class RuleRepairer:
    """
    Deterministic Rule-Based Repair Engine for MapleDoctor.
    Coordinates the 11 MapleDoctor rules, applying deterministic transformations
    when high-confidence conditions are met.
    """

    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb
        self.rules: List[MapleRule] = [
            FunctionHallucinationRule(),
            TableColumnMismatchRule(),
            UnusedAliasRule(),
            SchemaHallucinationRule(),
            MissingJoinRule(),
            ImplicitTypeConversionRule(),
            EqualsInsteadOfInRule(),
            AscendingSortWithNullRule(),
            ComparingUnrelatedColumnsRule(),
            ViolatingValueSpecificationRule(),
            AggregationComparisonMisuseRule(),
            SuspiciousSymptomsRule()
        ]

    def attempt_repair(
        self,
        sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite"
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Attempts deterministic repair using the rule matching the detection category.
        Returns:
            Tuple[repaired_sql, rule_name, confidence]
            If no deterministic rule applies or repair is ambiguous, returns (None, reason, 0.0).
        """
        for rule in self.rules:
            if rule.category == detection.category:
                if rule.can_repair(detection):
                    repaired_sql, rule_name, conf = rule.repair(
                        sql=sql,
                        detection=detection,
                        dataset=dataset,
                        database_id=database_id,
                        dialect=dialect,
                        kb=self.kb
                    )
                    if repaired_sql and conf > 0.0:
                        return repaired_sql, rule_name, conf

        return None, "No deterministic rule applies; requires LLM fallback", 0.0
