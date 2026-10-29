from typing import Optional, Dict, Any, List
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.detector.base import BaseDetector
from src.mapledoctor.detector.dbms_detector import DBMSDetector
from src.mapledoctor.detector.ast_detector import ASTDetector
from src.mapledoctor.detector.symptom_detector import SymptomDetector
from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
from src.mapledoctor.probes import DatabaseProber
from src.mapledoctor.ast_utils import parse_sql, extract_tables_and_aliases
from sqlglot import exp

class UniversalDetector:
    """
    Universal Rule-Based Error Detector for MapleDoctor.
    Coordinates DBMS error parsing, AST anti-pattern checks, schema verification,
    data/constraint probes, and suspicious symptom inspection.
    
    Strictly follows the paper's Execution-First Priority:
        1. Syntax & Function Errors
        2. Schema Errors (Mismatch, Unused Alias, Hallucination, Missing Join)
        3. Logic Errors (Type Conversion, = vs IN, ASC Null, Unrelated Columns)
        4. Convention Errors (Violating Value Spec, Aggregation Misuse)
        5. Suspicious Semantic Symptoms (Empty result, Single NULL)
    """

    def __init__(self, kb: Optional[KnowledgeBase] = None, prober: Optional[DatabaseProber] = None):
        self.kb = kb
        self.prober = prober or DatabaseProber()
        self.dbms_detector = DBMSDetector()
        self.ast_detector = ASTDetector()
        self.symptom_detector = SymptomDetector()

    def detect(
        self,
        sql: str,
        error_text: Optional[str] = None,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        db_path: str = "",
        execution_dict: Optional[Dict[str, Any]] = None,
        question: str = ""
    ) -> Optional[DetectionResult]:
        """Runs the prioritized detection pipeline and returns the highest priority error."""
        # 1. Check DBMS execution errors
        if error_text:
            dbms_res = self.dbms_detector.detect(
                sql=sql,
                error_text=error_text,
                dataset=dataset,
                database_id=database_id,
                dialect=dialect,
                db_path=db_path,
                kb=self.kb,
                prober=self.prober,
                execution_dict=execution_dict,
                question=question
            )
            if dbms_res:
                return dbms_res

        # 2. Check Static AST anti-patterns and logic errors
        ast_res = self.ast_detector.detect(
            sql=sql,
            error_text=error_text,
            dataset=dataset,
            database_id=database_id,
            dialect=dialect,
            db_path=db_path,
            kb=self.kb,
            prober=self.prober,
            execution_dict=execution_dict,
            question=question
        )
        if ast_res:
            return ast_res

        # 3. Check Rule 10: VIOLATING VALUE SPECIFICATION (Convention error)
        val_spec_res = self._check_value_specification(
            sql=sql,
            dataset=dataset,
            database_id=database_id,
            dialect=dialect,
            db_path=db_path
        )
        if val_spec_res:
            return val_spec_res

        # 4. Check Suspicious Execution Symptoms (Semantic errors proxy)
        if execution_dict:
            symptom_res = self.symptom_detector.detect(
                sql=sql,
                error_text=error_text,
                dataset=dataset,
                database_id=database_id,
                dialect=dialect,
                db_path=db_path,
                kb=self.kb,
                prober=self.prober,
                execution_dict=execution_dict,
                question=question
            )
            if symptom_res:
                return symptom_res

        return None

    def _check_value_specification(
        self,
        sql: str,
        dataset: str,
        database_id: str,
        dialect: str,
        db_path: str
    ) -> Optional[DetectionResult]:
        """Checks if WHERE equality predicates use a value violating column specification."""
        tree = parse_sql(sql, dialect=dialect)
        if not tree or not self.kb:
            return None

        tables_and_aliases = extract_tables_and_aliases(tree)
        schema = self.kb.get_schema(dataset, database_id)
        if not schema:
            return None

        # Look for col = 'literal'
        for eq in tree.find_all(exp.EQ):
            col = None
            literal = None
            if isinstance(eq.this, exp.Column) and isinstance(eq.expression, exp.Literal):
                col = eq.this
                literal = eq.expression
            elif isinstance(eq.expression, exp.Column) and isinstance(eq.this, exp.Literal):
                col = eq.expression
                literal = eq.this

            if col and literal and literal.is_string:
                col_name = col.name
                col_val = str(literal.this)
                # Find table
                tbl_ref = col.table or (list(tables_and_aliases.keys())[0] if tables_and_aliases else None)
                real_tbl = tables_and_aliases.get(tbl_ref.lower(), tbl_ref) if tbl_ref else None

                if real_tbl and real_tbl in schema.tables:
                    # Probe distinct values
                    distinct_vals = self.prober.probe_distinct_values(
                        table_name=real_tbl,
                        col_name=col_name,
                        limit=30,
                        dialect=dialect,
                        db_path=db_path,
                        dataset=dataset,
                        database_id=database_id
                    )
                    if distinct_vals:
                        str_distinct = [str(v) for v in distinct_vals]
                        # Exact match exists?
                        if col_val not in str_distinct:
                            # Case-insensitive or stripped match?
                            case_matches = [v for v in str_distinct if v.lower() == col_val.lower()]
                            if case_matches:
                                return DetectionResult(
                                    category=ErrorCategory.VIOLATING_VALUE_SPECIFICATION,
                                    description=(
                                        f"Column '{col_name}' equality comparison '{col_val}' violates value specification. "
                                        f"Valid matching specification is '{case_matches[0]}'."
                                    ),
                                    location=ErrorLocation(clause="WHERE", table=real_tbl, column=col_name, operator="="),
                                    confidence=0.90,
                                    rule_name="MapleDoctor_Rule10_ViolatingValueSpecification",
                                    is_rule_applicable=False, # LLM-assisted
                                    evidence={
                                        "table": real_tbl,
                                        "column": col_name,
                                        "target_value": col_val,
                                        "valid_values": str_distinct,
                                        "recommended_value": case_matches[0]
                                    }
                                )

        return None
