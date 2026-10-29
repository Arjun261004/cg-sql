import re
from typing import Dict, Any, Optional, Tuple, List
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.models.state import SchemaLinkingResult
from src.mapledoctor.prompts.repair_prompts import MapleDoctorPromptBuilder
from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation

class LLMRepairer:
    """
    Internal Constrained LLM Repairer for RepairAgent.
    Fallback repair engine used ONLY when deterministic MAPLEDoctor rules cannot resolve the issue.
    Constrained by actual KB schema facts, relationships, and dialect restrictions.
    Follows MapleDoctor's 6-section error-specific prompt design.
    """
    def __init__(self, kb: Optional[KnowledgeBase] = None, llm_client: Optional[Any] = None):
        self.kb = kb
        self._llm_client = llm_client

    def repair_sql(
        self,
        original_query: str,
        failed_sql: str,
        error_text: str,
        classification: Dict[str, Any],
        schema_linking: Optional[SchemaLinkingResult] = None,
        dialect: str = "SQLite"
    ) -> Tuple[Optional[str], float]:
        """Invokes LLM with strict MapleDoctor constraints to repair the SQL."""
        try:
            if self._llm_client:
                llm = self._llm_client
            else:
                from src.core.llm_client import LLMClient
                llm = LLMClient()

            category_str = classification.get("category", "UNKNOWN")
            try:
                category_enum = ErrorCategory(category_str)
            except Exception:
                category_enum = ErrorCategory.UNKNOWN

            details = classification.get("details", {})
            location = ErrorLocation(
                clause="SELECT/WHERE",
                table=details.get("table"),
                column=details.get("column"),
                function=details.get("function")
            )

            detection = DetectionResult(
                category=category_enum,
                description=f"SQL error ({category_str}): {error_text}",
                location=location,
                confidence=0.75,
                raw_error=error_text,
                evidence=details
            )

            schema_context: Dict[str, Any] = {}
            if schema_linking:
                schema_context = {
                    "tables": schema_linking.final_tables,
                    "columns": schema_linking.final_columns
                }
            elif self.kb:
                pass

            prompt = MapleDoctorPromptBuilder.build_repair_prompt(
                question=original_query,
                failed_sql=failed_sql,
                detection=detection,
                schema_context=schema_context,
                dialect=dialect
            )

            repaired = llm.generate_text(prompt)
            if not repaired:
                return None, 0.0

            repaired = repaired.strip()
            if repaired.startswith("```sql"):
                repaired = repaired[6:]
            if repaired.startswith("```"):
                repaired = repaired[3:]
            if repaired.endswith("```"):
                repaired = repaired[:-3]
            repaired = repaired.strip().rstrip(";")

            if repaired and repaired != failed_sql:
                return repaired, 0.85
            return None, 0.0

        except Exception as e:
            print(f"LLMRepairer failed: {e}")
            return None, 0.0
