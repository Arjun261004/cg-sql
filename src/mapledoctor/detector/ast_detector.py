import re
from typing import Optional, Dict, Any, List
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.mapledoctor.detector.base import BaseDetector
from src.mapledoctor.models import DetectionResult, ErrorCategory, ErrorLocation
from src.mapledoctor.probes import DatabaseProber
from src.mapledoctor.ast_utils import (
    parse_sql,
    extract_tables_and_aliases,
    extract_columns,
    extract_functions,
    extract_division_nodes,
    is_integer_operand,
    has_float_cast,
    extract_subquery_equalities,
    extract_order_by_columns,
    extract_min_max_columns,
    has_null_filter,
    extract_join_equalities
)

SQLITE_UNSUPPORTED_FUNCTIONS = {
    "DIVIDE": "operator /",
    "YEAR": "strftime('%Y', col)",
    "MONTH": "strftime('%m', col)",
    "DAY": "strftime('%d', col)",
    "DATE_TRUNC": "strftime",
    "NOW": "CURRENT_TIMESTAMP",
    "POW": "POWER",
}

class ASTDetector(BaseDetector):
    """
    Performs static SQL AST inspection to detect anti-patterns and logic errors:
    - Rule 1: FUNCTION_HALLUCINATION (dialect unsupported functions)
    - Rule 3: UNUSED_ALIAS (table has alias but original name referenced)
    - Rule 6: IMPLICIT_TYPE_CONVERSION (integer / integer without CAST)
    - Rule 7: EQUALS_INSTEAD_OF_IN (equality against multi-row subquery)
    - Rule 8: ASCENDING_SORT_WITH_NULL (ORDER BY ASC or MIN without NULL filter)
    - Rule 9: COMPARING_UNRELATED_COLUMNS (JOIN equality between non-FK columns)
    - Rule 11: AGGREGATION_COMPARISON_MISUSE (numeric aggregate or sorting on text columns)
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
        tree = parse_sql(sql, dialect=dialect)
        if not tree:
            return None

        # 1. RULE 1: FUNCTION HALLUCINATION (AST check)
        funcs = extract_functions(tree)
        for fname, fargs in funcs:
            if dialect == "SQLite" and fname in SQLITE_UNSUPPORTED_FUNCTIONS:
                return DetectionResult(
                    category=ErrorCategory.FUNCTION_HALLUCINATION,
                    description=f"Function '{fname}' is unsupported in {dialect}; use {SQLITE_UNSUPPORTED_FUNCTIONS[fname]}.",
                    location=ErrorLocation(clause="SELECT", function=fname),
                    confidence=0.98,
                    rule_name="MapleDoctor_Rule1_FunctionHallucination",
                    is_rule_applicable=True,
                    evidence={"function": fname, "unsupported_in": dialect}
                )

        # 2. RULE 3: UNUSED ALIAS (AST check)
        tables_and_aliases = extract_tables_and_aliases(tree)
        for tbl_lower, alias in tables_and_aliases.items():
            if alias.lower() != tbl_lower:
                # Table has an alias assigned
                for col_tbl, col_name in extract_columns(tree):
                    if col_tbl and col_tbl.lower() == tbl_lower:
                        return DetectionResult(
                            category=ErrorCategory.UNUSED_ALIAS,
                            description=f"Table '{col_tbl}' is aliased as '{alias}', but column reference used original table name.",
                            location=ErrorLocation(table=col_tbl, column=col_name),
                            confidence=0.98,
                            rule_name="MapleDoctor_Rule3_UnusedAlias",
                            is_rule_applicable=True,
                            evidence={"table": col_tbl, "alias": alias, "column": col_name}
                        )

        # 3. RULE 6: IMPLICIT TYPE CONVERSION
        div_nodes = extract_division_nodes(tree)
        for div in div_nodes:
            left = div.this
            right = div.expression
            if not has_float_cast(left) and not has_float_cast(right):
                left_int = is_integer_operand(left)
                right_int = is_integer_operand(right)
                # If either or both operands are integers or COUNT, flag implicit integer division
                if left_int or right_int:
                    return DetectionResult(
                        category=ErrorCategory.IMPLICIT_TYPE_CONVERSION,
                        description=f"Division node '{div.sql()}' uses integer operands without an explicit floating-point CAST.",
                        location=ErrorLocation(clause="SELECT", operator="/"),
                        confidence=0.95,
                        rule_name="MapleDoctor_Rule6_ImplicitTypeConversion",
                        is_rule_applicable=True,
                        evidence={"division": div.sql(), "left": left.sql(), "right": right.sql()}
                    )

        # 4. RULE 7: USING "=" INSTEAD OF "IN"
        subq_equalities = extract_subquery_equalities(tree)
        for eq_node, col_node, subq_node in subq_equalities:
            subq_sql = subq_node.sql()
            # If subquery has no LIMIT 1 and no scalar aggregate without GROUP BY
            has_limit_one = bool(re.search(r'\bLIMIT\s+1\b', subq_sql, re.IGNORECASE))
            has_scalar_agg_no_group = bool(
                re.search(r'\b(MAX|MIN|COUNT|AVG|SUM)\s*\(', subq_sql, re.IGNORECASE)
                and not re.search(r'\bGROUP\s+BY\b', subq_sql, re.IGNORECASE)
            )
            if not has_limit_one and not has_scalar_agg_no_group:
                # Subquery can return multiple rows
                # Check probe if available
                can_return_multiple = True
                if prober:
                    cnt = prober.probe_subquery_row_count(
                        subq_sql,
                        dialect=dialect,
                        db_path=db_path,
                        dataset=dataset,
                        database_id=database_id
                    )
                    can_return_multiple = (cnt > 1)

                if can_return_multiple:
                    return DetectionResult(
                        category=ErrorCategory.EQUALS_INSTEAD_OF_IN,
                        description=f"Comparison '{col_node.sql()} = ({subq_sql})' uses '=' but subquery represents a multi-row set.",
                        location=ErrorLocation(clause="WHERE", column=col_node.name, operator="="),
                        confidence=0.95,
                        rule_name="MapleDoctor_Rule7_EqualsInsteadOfIn",
                        is_rule_applicable=True,
                        evidence={"column": col_node.name, "subquery": subq_sql}
                    )

        # 5. RULE 8: ASCENDING SORT WITH NULL
        # Check ORDER BY columns
        for col_name, tbl_name, is_asc in extract_order_by_columns(tree):
            if is_asc:
                # Check if NULL is filtered
                if not has_null_filter(tree, col_name, tbl_name):
                    # Probe if column contains NULL
                    target_table = tbl_name or list(tables_and_aliases.keys())[0] if tables_and_aliases else None
                    has_nulls = False
                    if prober and target_table:
                        has_nulls = prober.probe_column_has_nulls(
                            target_table,
                            col_name,
                            dialect=dialect,
                            db_path=db_path,
                            dataset=dataset,
                            database_id=database_id
                        )
                    if has_nulls:
                        return DetectionResult(
                            category=ErrorCategory.ASCENDING_SORT_WITH_NULL,
                            description=f"Ascending sort on column '{col_name}' which contains NULL values may select NULL as the first/minimum row.",
                            location=ErrorLocation(clause="ORDER BY", column=col_name, table=tbl_name),
                            confidence=0.92,
                            rule_name="MapleDoctor_Rule8_AscendingSortWithNull",
                            is_rule_applicable=True,
                            evidence={"column": col_name, "table": target_table, "operation": "ORDER BY ASC"}
                        )

        # Check MIN() columns
        for op, col_name, tbl_name in extract_min_max_columns(tree):
            if op == "MIN":
                if not has_null_filter(tree, col_name, tbl_name):
                    target_table = tbl_name or (list(tables_and_aliases.keys())[0] if tables_and_aliases else None)
                    has_nulls = False
                    if prober and target_table:
                        has_nulls = prober.probe_column_has_nulls(
                            target_table,
                            col_name,
                            dialect=dialect,
                            db_path=db_path,
                            dataset=dataset,
                            database_id=database_id
                        )
                    if has_nulls:
                        return DetectionResult(
                            category=ErrorCategory.ASCENDING_SORT_WITH_NULL,
                            description=f"MIN({col_name}) on column containing NULL values without IS NOT NULL filter.",
                            location=ErrorLocation(clause="SELECT", column=col_name, table=tbl_name, function="MIN"),
                            confidence=0.90,
                            rule_name="MapleDoctor_Rule8_AscendingSortWithNull",
                            is_rule_applicable=True,
                            evidence={"column": col_name, "table": target_table, "operation": "MIN"}
                        )

        # 6. RULE 9: COMPARING UNRELATED COLUMNS (Algorithm 1)
        join_eqs = extract_join_equalities(tree)
        for join_node, eq_node, (l_tbl, l_col), (r_tbl, r_col) in join_eqs:
            # Resolve actual table names from aliases if needed
            alias_to_tbl = {v.lower(): k for k, v in tables_and_aliases.items()}
            real_l_tbl = alias_to_tbl.get(l_tbl.lower(), l_tbl)
            real_r_tbl = alias_to_tbl.get(r_tbl.lower(), r_tbl)

            if real_l_tbl and real_r_tbl and real_l_tbl.lower() != real_r_tbl.lower():
                # Check if FK relationship exists between them
                is_fk = False
                if kb:
                    rels = kb.get_relationships(dataset, database_id)
                    for r in rels:
                        r_dict = r.model_dump() if hasattr(r, "model_dump") else (r.dict() if hasattr(r, "dict") else r)
                        s_t = r_dict.get("source_table", "").lower()
                        s_c = r_dict.get("source_column", "").lower()
                        t_t = r_dict.get("target_table", "").lower()
                        t_c = r_dict.get("target_column", "").lower()
                        if (s_t == real_l_tbl.lower() and s_c == l_col.lower() and t_t == real_r_tbl.lower() and t_c == r_col.lower()) or \
                           (s_t == real_r_tbl.lower() and s_c == r_col.lower() and t_t == real_l_tbl.lower() and t_c == l_col.lower()):
                            is_fk = True
                            break

                if not is_fk:
                    # Execute Paper Algorithm 1 probe: value overlap
                    has_overlap = True
                    if prober:
                        has_overlap = prober.probe_value_overlap(
                            real_l_tbl,
                            l_col,
                            real_r_tbl,
                            r_col,
                            dialect=dialect,
                            db_path=db_path,
                            dataset=dataset,
                            database_id=database_id
                        )

                    if not has_overlap:
                        # Algorithm 1: probe returns EMPTY -> Flag as error!
                        # Search for actual FK candidates
                        candidate_fks = []
                        if kb:
                            rels = kb.get_relationships(dataset, database_id)
                            for r in rels:
                                r_dict = r.dict() if hasattr(r, "dict") else r
                                s_t = r_dict.get("source_table", "").lower()
                                t_t = r_dict.get("target_table", "").lower()
                                if (s_t == real_l_tbl.lower() and t_t == real_r_tbl.lower()) or \
                                   (s_t == real_r_tbl.lower() and t_t == real_l_tbl.lower()):
                                    candidate_fks.append(r_dict)

                        is_single_fk = len(candidate_fks) == 1
                        return DetectionResult(
                            category=ErrorCategory.COMPARING_UNRELATED_COLUMNS,
                            description=(
                                f"JOIN equality '{l_tbl}.{l_col} = {r_tbl}.{r_col}' compares unrelated columns "
                                f"with no foreign-key relationship and 0 overlapping values."
                            ),
                            location=ErrorLocation(clause="JOIN", operator="=", predicate=f"{l_tbl}.{l_col} = {r_tbl}.{r_col}"),
                            confidence=0.95 if is_single_fk else 0.75,
                            rule_name="MapleDoctor_Rule9_ComparingUnrelatedColumns",
                            is_rule_applicable=is_single_fk,
                            evidence={
                                "left": f"{real_l_tbl}.{l_col}",
                                "right": f"{real_r_tbl}.{r_col}",
                                "candidate_fks": candidate_fks,
                                "probe_empty": True
                            }
                        )

        # 7. RULE 11: AGGREGATION / COMPARISON MISUSE (AST check)
        if kb:
            schema = kb.get_schema(dataset, database_id)
            if schema:
                # Check for MAX/MIN or ORDER BY on TEXT columns with numeric data
                for op, col_name, tbl_name in extract_min_max_columns(tree):
                    tbl = tbl_name or (list(tables_and_aliases.keys())[0] if tables_and_aliases else None)
                    if tbl and tbl in schema.tables:
                        col_schema = schema.tables[tbl].columns.get(col_name)
                        col_type = (getattr(col_schema, "type", None) or getattr(col_schema, "data_type", None) or "")
                        if col_schema and col_type and col_type.upper() in ["TEXT", "VARCHAR", "CHAR"]:
                            # Probe sample values to see if they are numeric
                            sample_vals = prober.probe_sample_values(tbl, col_name, 5, dialect, db_path, dataset, database_id) if prober else []
                            numeric_looking = len(sample_vals) > 0 and all(str(v).replace('.', '', 1).isdigit() for v in sample_vals)
                            if numeric_looking:
                                return DetectionResult(
                                    category=ErrorCategory.AGGREGATION_COMPARISON_MISUSE,
                                    description=f"{op}() on TEXT column '{col_name}' containing numeric values causes lexicographical evaluation.",
                                    location=ErrorLocation(clause="SELECT", column=col_name, table=tbl, function=op),
                                    confidence=0.88,
                                    rule_name="MapleDoctor_Rule11_AggregationComparisonMisuse",
                                    is_rule_applicable=False, # LLM-assisted
                                    evidence={"column": col_name, "type": "TEXT", "sample_values": sample_vals, "operation": op}
                                )

        return None
