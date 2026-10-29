import re
import difflib
from typing import Optional, Dict, Any, List
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.detector.base import BaseDetector
from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
from src.mapledoctor.probes import DatabaseProber
from src.mapledoctor.ast_utils import parse_sql, extract_tables_and_aliases, extract_columns

class DBMSDetector(BaseDetector):
    """
    Detects errors originating from DBMS execution messages and parses error details.
    Disambiguates 'no such column' into:
    - Rule 3: UNUSED_ALIAS
    - Rule 2: TABLE_COLUMN_MISMATCH
    - Rule 5: MISSING_JOIN
    - Rule 4: SCHEMA_HALLUCINATION
    Also detects:
    - Rule 1: FUNCTION_HALLUCINATION
    - Rule 7: EQUALS_INSTEAD_OF_IN (from runtime subquery errors)
    """

    def detect(
        self,
        sql: str,
        error_text: Optional[str] = None,
        dataset: str = "spider",
        database_id: str = "default",
        dialect: str = "SQLite",
        db_path: str = "",
        kb: Optional[KnowledgeBase] = None,
        prober: Optional[DatabaseProber] = None,
        execution_dict: Optional[Dict[str, Any]] = None,
        question: str = ""
    ) -> Optional[DetectionResult]:
        if not error_text:
            return None

        err_lower = error_text.lower()

        # 1. FUNCTION HALLUCINATION (Rule 1)
        if "no such function" in err_lower or "unknown function" in err_lower:
            fn_match = re.search(r'function:?\s*([a-zA-Z0-9_]+)', error_text, re.IGNORECASE)
            fn_name = fn_match.group(1) if fn_match else ""
            if not fn_name:
                for fn in ["DIVIDE", "YEAR", "MONTH", "DAY", "CONCAT", "NOW", "DATE_TRUNC", "POW", "POWER"]:
                    if fn.lower() in err_lower or fn in sql.upper():
                        fn_name = fn
                        break
            return DetectionResult(
                category=ErrorCategory.FUNCTION_HALLUCINATION,
                description=f"DBMS error: Unsupported or hallucinated function '{fn_name}' for {dialect}.",
                location=ErrorLocation(clause="SELECT", function=fn_name),
                confidence=0.98,
                rule_name="MapleDoctor_Rule1_FunctionHallucination",
                is_rule_applicable=True,
                evidence={"function": fn_name, "raw_error": error_text},
                raw_error=error_text
            )

        # 2. EQUALS INSTEAD OF IN (Rule 7 via runtime subquery error)
        if "more than one row returned by a subquery" in err_lower or "subquery returns more than 1 row" in err_lower or "subquery returned more than 1 row" in err_lower:
            return DetectionResult(
                category=ErrorCategory.EQUALS_INSTEAD_OF_IN,
                description="DBMS error: Subquery used in comparison returned multiple rows. '=' operator requires single scalar value.",
                location=ErrorLocation(clause="WHERE", operator="="),
                confidence=0.98,
                rule_name="MapleDoctor_Rule7_EqualsInsteadOfIn",
                is_rule_applicable=True,
                evidence={"subquery_error": True, "raw_error": error_text},
                raw_error=error_text
            )

        # 3. NO SUCH COLUMN DISAMBIGUATION (Rules 2, 3, 4, 5)
        col_match = re.search(r'no such column:?\s*([a-zA-Z0-9_.]+)', error_text, re.IGNORECASE)
        if not col_match:
            col_match = re.search(r'(?:referenced\s+)?column\s+["\']?([a-zA-Z0-9_.]+)["\']?\s+does not exist', error_text, re.IGNORECASE)

        if col_match:
            full_ref = col_match.group(1).strip()
            parts = full_ref.split('.')
            col_name = parts[-1]
            table_ref = parts[0] if len(parts) > 1 else None

            # Parse AST to check table aliases and referenced tables
            tree = parse_sql(sql, dialect=dialect)
            tables_and_aliases = extract_tables_and_aliases(tree) if tree else {}
            # Reverse mapping: table_name -> alias
            schema = kb.get_schema(dataset, database_id) if kb else None

            # Check Rule 3: UNUSED ALIAS
            if table_ref:
                t_lower = table_ref.lower()
                # Check if table_ref is an actual table name that was given a different alias in SQL
                if t_lower in tables_and_aliases:
                    assigned_alias = tables_and_aliases[t_lower]
                    if assigned_alias.lower() != t_lower:
                        return DetectionResult(
                            category=ErrorCategory.UNUSED_ALIAS,
                            description=f"Table '{table_ref}' has assigned alias '{assigned_alias}', but column reference used original table name.",
                            location=ErrorLocation(table=table_ref, column=col_name),
                            confidence=0.98,
                            rule_name="MapleDoctor_Rule3_UnusedAlias",
                            is_rule_applicable=True,
                            evidence={"table": table_ref, "alias": assigned_alias, "column": col_name},
                            raw_error=error_text
                        )

            # Check Schema Existence
            if schema:
                all_tables = schema.tables
                tables_with_col: List[str] = []
                for tname, tinfo in all_tables.items():
                    for cname in tinfo.columns.keys():
                        if cname.lower() == col_name.lower():
                            tables_with_col.append(tname)
                            break

                current_query_tables = list(tables_and_aliases.keys())

                # Check Rule 2: TABLE_COLUMN_MISMATCH
                if table_ref and tables_with_col:
                    if table_ref.lower() not in [t.lower() for t in tables_with_col]:
                        # Column exists, but NOT in table_ref
                        is_single = len(tables_with_col) == 1
                        return DetectionResult(
                            category=ErrorCategory.TABLE_COLUMN_MISMATCH,
                            description=f"Column '{col_name}' does not exist in table '{table_ref}', but exists in {tables_with_col}.",
                            location=ErrorLocation(table=table_ref, column=col_name),
                            confidence=0.95 if is_single else 0.70,
                            rule_name="MapleDoctor_Rule2_TableColumnMismatch",
                            is_rule_applicable=is_single,
                            evidence={"wrong_table": table_ref, "matching_tables": tables_with_col, "column": col_name},
                            raw_error=error_text
                        )

                # Check Rule 5: MISSING JOIN
                if tables_with_col:
                    unjoined_tables = [t for t in tables_with_col if t.lower() not in current_query_tables]
                    if unjoined_tables:
                        # Find foreign key paths to connect unjoined table
                        candidate_fk_paths = []
                        target_unjoined = unjoined_tables[0]
                        for q_tbl in current_query_tables:
                            paths = kb.find_join_paths(dataset, database_id, target_unjoined, q_tbl) if kb else []
                            for p in paths:
                                candidate_fk_paths.append((target_unjoined, q_tbl, p))

                        is_single_fk = len(candidate_fk_paths) == 1
                        return DetectionResult(
                            category=ErrorCategory.MISSING_JOIN,
                            description=f"Column '{col_name}' belongs to unjoined table '{target_unjoined}'.",
                            location=ErrorLocation(table=target_unjoined, column=col_name),
                            confidence=0.92 if is_single_fk else 0.70,
                            rule_name="MapleDoctor_Rule5_MissingJoin",
                            is_rule_applicable=is_single_fk,
                            evidence={
                                "unjoined_table": target_unjoined,
                                "column": col_name,
                                "fk_paths_count": len(candidate_fk_paths),
                                "candidate_paths": [str(p) for _, _, p in candidate_fk_paths]
                            },
                            raw_error=error_text
                        )

                # If col does NOT exist in any table: Rule 4: SCHEMA HALLUCINATION
                if not tables_with_col:
                    # Find similar columns via edit distance
                    candidate_cols = []
                    all_schema_cols = []
                    for tname in (current_query_tables or all_tables.keys()):
                        t_schema = all_tables.get(tname)
                        if t_schema:
                            all_schema_cols.extend(list(t_schema.columns.keys()))

                    # Find matches with high similarity
                    close_matches = difflib.get_close_matches(col_name, all_schema_cols, n=3, cutoff=0.6)
                    is_confident_match = False
                    best_match = None
                    if close_matches:
                        best_match = close_matches[0]
                        ratio = difflib.SequenceMatcher(None, col_name.lower(), best_match.lower()).ratio()
                        if ratio >= 0.70 and (len(close_matches) == 1 or ratio - difflib.SequenceMatcher(None, col_name.lower(), close_matches[1].lower()).ratio() >= 0.15):
                            is_confident_match = True

                    return DetectionResult(
                        category=ErrorCategory.SCHEMA_HALLUCINATION,
                        description=f"Referenced column '{col_name}' does not exist in schema." + (f" Suggested candidate: '{best_match}'" if best_match else ""),
                        location=ErrorLocation(column=col_name, table=table_ref),
                        confidence=0.90 if is_confident_match else 0.60,
                        rule_name="MapleDoctor_Rule4_SchemaHallucination",
                        is_rule_applicable=is_confident_match,
                        evidence={"hallucinated_column": col_name, "close_matches": close_matches, "best_match": best_match},
                        raw_error=error_text
                    )

        # 4. NO SUCH TABLE (Rule 4: SCHEMA HALLUCINATION for tables)
        tbl_match = re.search(r'no such table:?\s*([a-zA-Z0-9_]+)', error_text, re.IGNORECASE)
        if not tbl_match:
            tbl_match = re.search(r'(?:referenced\s+)?table\s+["\']?([a-zA-Z0-9_]+)["\']?\s+does not exist', error_text, re.IGNORECASE)
        if tbl_match:
            tbl_name = tbl_match.group(1).strip()
            best_match = None
            is_confident = False
            if kb:
                schema = kb.get_schema(dataset, database_id)
                if schema:
                    known_tables = list(schema.tables.keys())
                    matches = difflib.get_close_matches(tbl_name, known_tables, n=3, cutoff=0.6)
                    if matches:
                        best_match = matches[0]
                        is_confident = True

            return DetectionResult(
                category=ErrorCategory.SCHEMA_HALLUCINATION,
                description=f"Table '{tbl_name}' does not exist in schema." + (f" Suggested: '{best_match}'" if best_match else ""),
                location=ErrorLocation(table=tbl_name),
                confidence=0.90 if is_confident else 0.50,
                rule_name="MapleDoctor_Rule4_SchemaHallucination",
                is_rule_applicable=is_confident,
                evidence={"hallucinated_table": tbl_name, "best_match": best_match},
                raw_error=error_text
            )

        # Generic syntax error
        if "syntax error" in err_lower or "parse error" in err_lower or "near " in err_lower:
            return DetectionResult(
                category=ErrorCategory.SYNTAX_ERROR,
                description=f"SQL syntax error: {error_text}",
                confidence=0.80,
                rule_name="SyntaxError",
                is_rule_applicable=False,
                raw_error=error_text
            )

        return None
