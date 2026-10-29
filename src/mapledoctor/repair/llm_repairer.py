import re
from typing import Optional, Tuple, Dict, Any, List
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.models import DetectionResult, ErrorCategory
from src.mapledoctor.prompts.repair_prompts import MapleDoctorPromptBuilder
from src.mapledoctor.ast_utils import parse_sql

class MapleDoctorLLMRepairer:
    """
    Constrained LLM Repairer for MapleDoctor.
    Invoked ONLY when deterministic rules cannot resolve the error,
    when multiple candidate repair options exist (ambiguity), or
    when semantic interpretation is required.
    
    Constructs an error-specific, 6-section prompt with schema and foreign-key bounds.
    """

    def __init__(self, kb: Optional[KnowledgeBase] = None, llm_client: Optional[Any] = None):
        self.kb = kb
        self._custom_llm_client = llm_client

    def _get_llm_client(self):
        if self._custom_llm_client:
            return self._custom_llm_client
        try:
            from src.core.llm_client import LLMClient
            return LLMClient()
        except Exception:
            return None

    def repair(
        self,
        question: str,
        failed_sql: str,
        detection: DetectionResult,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite"
    ) -> Tuple[Optional[str], float]:
        """
        Executes constrained LLM repair using error-specific prompt.
        Returns:
            Tuple[repaired_sql, confidence]
        """
        llm = self._get_llm_client()
        if not llm:
            return None, 0.0

        # Build schema context and foreign-key info from KB
        schema_context: Dict[str, Any] = {}
        foreign_keys: List[Dict[str, Any]] = []
        if self.kb:
            schema = self.kb.get_schema(dataset, database_id)
            if schema:
                schema_context["tables"] = list(schema.tables.keys())
                schema_context["columns"] = {
                    t: list(info.columns.keys()) for t, info in schema.tables.items()
                }
            rels = self.kb.get_relationships(dataset, database_id)
            for r in rels:
                r_dict = r.model_dump() if hasattr(r, "model_dump") else (r.dict() if hasattr(r, "dict") else r)
                foreign_keys.append(r_dict)

        # Candidates / recommendations from detection evidence
        candidates = None
        if "matching_tables" in detection.evidence:
            candidates = detection.evidence["matching_tables"]
        elif "candidate_fks" in detection.evidence:
            candidates = [f"{fk.get('source_table')}.{fk.get('source_column')} = {fk.get('target_table')}.{fk.get('target_column')}" for fk in detection.evidence["candidate_fks"]]
        elif "close_matches" in detection.evidence:
            candidates = detection.evidence["close_matches"]

        valid_values = detection.evidence.get("valid_values")

        prompt = MapleDoctorPromptBuilder.build_repair_prompt(
            question=question or "Translate user request to SQL",
            failed_sql=failed_sql,
            detection=detection,
            schema_context=schema_context,
            foreign_keys=foreign_keys,
            dialect=dialect,
            candidates=candidates,
            valid_values=valid_values
        )

        try:
            raw_response = llm.generate_text(prompt)
            if not raw_response:
                return None, 0.0

            # Clean markdown code blocks
            repaired = raw_response.strip()
            if repaired.startswith("```sql"):
                repaired = repaired[6:]
            elif repaired.startswith("```"):
                repaired = repaired[3:]
            if repaired.endswith("```"):
                repaired = repaired[:-3]
            repaired = repaired.strip().rstrip(";")

            # Safety check: ensure repaired query parses
            tree = parse_sql(repaired, dialect=dialect)
            if tree and repaired != failed_sql:
                return repaired, 0.85

            return None, 0.0

        except Exception as e:
            return None, 0.0
