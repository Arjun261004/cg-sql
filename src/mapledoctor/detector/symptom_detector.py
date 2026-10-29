from typing import Optional, Dict, Any
from src.mapledoctor.detector.base import BaseDetector
from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation

class SymptomDetector(BaseDetector):
    """
    Detects suspicious execution symptoms used by MapleDoctor as proxies for semantic errors:
    1. EMPTY_RESULT (0 rows returned)
    2. SINGLE_NULL_RESULT (1 row containing a single NULL value)
    
    IMPORTANT SAFETY RULE:
    Empty/NULL results are NOT automatic proof of an error. They are signals
    for targeted semantic investigation and LLM-assisted verification.
    """

    def detect(
        self,
        sql: str,
        error_text: Optional[str] = None,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        db_path: str = "",
        kb: Optional[Any] = None,
        prober: Optional[Any] = None,
        execution_dict: Optional[Dict[str, Any]] = None,
        question: str = ""
    ) -> Optional[DetectionResult]:
        if not execution_dict or execution_dict.get("status") != "success":
            return None

        rows = execution_dict.get("rows", 0)
        data = execution_dict.get("data", [])

        # 1. Suspicious Empty Result
        if rows == 0 or len(data) == 0:
            return DetectionResult(
                category=ErrorCategory.EMPTY_RESULT,
                description="Query executed successfully but returned 0 rows. Suspicious symptom indicating possible over-restrictive filter or incorrect join.",
                location=ErrorLocation(clause="WHERE"),
                confidence=0.70,
                rule_name="MapleDoctor_Symptom_EmptyResult",
                is_rule_applicable=False,  # Semantic, requires LLM reasoning
                evidence={"rows": 0, "status": "success", "question": question}
            )

        # 2. Suspicious Single NULL Result
        if rows == 1 and len(data) == 1:
            first_row = data[0]
            if len(first_row) == 1 and (first_row[0] is None or str(first_row[0]).upper() == "NONE" or str(first_row[0]).upper() == "NULL"):
                return DetectionResult(
                    category=ErrorCategory.SINGLE_NULL_RESULT,
                    description="Query returned a single NULL result. May indicate aggregate over empty filtered set or incorrect column selection.",
                    location=ErrorLocation(clause="SELECT"),
                    confidence=0.72,
                    rule_name="MapleDoctor_Symptom_SingleNullResult",
                    is_rule_applicable=False,  # Semantic, requires LLM reasoning
                    evidence={"row": first_row, "status": "success", "question": question}
                )

        return None
