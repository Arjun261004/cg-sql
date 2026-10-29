from typing import Dict, List, Any, Optional
from src.mapledoctor.models import DetectionResult, ErrorLocation

class MapleDoctorPromptBuilder:
    """
    Constructs constrained, error-specific LLM repair prompts for MapleDoctor.
    Strictly structures every prompt into the 6 sections required by the MapleDoctor paper:
    1. CONTEXT (NL question, allowed schema, foreign keys, failed SQL)
    2. ERROR DESCRIPTION (Exact error type & explanation)
    3. ERROR LOCATION (Clause, table, column, operator, AST path)
    4. EXECUTION INFORMATION (DBMS error, probe result, symptoms)
    5. REPAIR INSTRUCTION (Targeted repair strategy, candidate options)
    6. SAFETY CONSTRAINTS (Conservative minimal fix, no hallucinations, preservation of intent)
    """

    @staticmethod
    def build_repair_prompt(
        question: str,
        failed_sql: str,
        detection: DetectionResult,
        schema_context: Optional[Dict[str, Any]] = None,
        foreign_keys: Optional[List[Dict[str, Any]]] = None,
        dialect: str = "SQLite",
        candidates: Optional[List[str]] = None,
        valid_values: Optional[List[Any]] = None
    ) -> str:
        loc = detection.location

        # 1. CONTEXT
        tables_str = ""
        columns_str = ""
        if schema_context:
            tables_str = str(schema_context.get("tables", []))
            columns_str = str(schema_context.get("columns", {}))

        fk_str = ""
        if foreign_keys:
            fk_str = "\n".join([f"- {fk.get('column')} -> {fk.get('target_table')}.{fk.get('target_column')}" for fk in foreign_keys[:10]])
        else:
            fk_str = "None specified"

        context_sec = f"""### 1. CONTEXT
- Natural-Language Question: "{question}"
- Target DBMS Dialect: {dialect}
- Database Tables: {tables_str}
- Table Columns: {columns_str}
- Foreign-Key Information:
{fk_str}

Erroneous SQL Query:
```sql
{failed_sql}
```"""

        # 2. ERROR DESCRIPTION
        error_sec = f"""### 2. ERROR DESCRIPTION
- Detected Error Category: {detection.category.value}
- Error Rule: {detection.rule_name or 'N/A'}
- Explanation: {detection.description}"""

        # 3. ERROR LOCATION
        location_parts = []
        if loc.clause:
            location_parts.append(f"Clause: {loc.clause}")
        if loc.table:
            location_parts.append(f"Table: {loc.table}")
        if loc.column:
            location_parts.append(f"Column: {loc.column}")
        if loc.operator:
            location_parts.append(f"Operator: {loc.operator}")
        if loc.function:
            location_parts.append(f"Function: {loc.function}")
        if loc.predicate:
            location_parts.append(f"Predicate: {loc.predicate}")
        if loc.ast_path:
            location_parts.append(f"AST Location: {loc.ast_path}")

        location_sec = f"""### 3. ERROR LOCATION
{chr(10).join('- ' + p for p in location_parts) if location_parts else '- Location inferred from query AST and error context'}"""

        # 4. EXECUTION INFORMATION
        exec_parts = []
        if detection.raw_error:
            exec_parts.append(f"DBMS Error Message: {detection.raw_error}")
        if detection.probe_result:
            exec_parts.append(f"Probe Result: {detection.probe_result}")
        if detection.evidence:
            exec_parts.append(f"Diagnostic Evidence: {detection.evidence}")

        exec_sec = f"""### 4. EXECUTION INFORMATION
{chr(10).join('- ' + p for p in exec_parts) if exec_parts else '- No runtime DBMS crash (detected via AST or probe)'}"""

        # 5. REPAIR INSTRUCTION
        candidates_str = ""
        if candidates:
            candidates_str = f"\nCandidate Options to consider: {candidates}"
        if valid_values:
            candidates_str += f"\nKnown Valid Specification Values: {valid_values}"

        repair_sec = f"""### 5. REPAIR INSTRUCTION
Apply a targeted, minimal surgical repair for the detected {detection.category.value}.
Repair Focus: {detection.description}{candidates_str}
Do not rewrite the query from scratch. Make ONLY the targeted correction required to resolve this error."""

        # 6. SAFETY CONSTRAINTS
        constraints_sec = f"""### 6. SAFETY CONSTRAINTS
- PRESERVE the original user intent.
- DO NOT invent tables or columns not present in the allowed schema.
- DO NOT invent foreign-key relationships.
- DO NOT remove required filter conditions.
- DO NOT change unrelated portions of the query.
- DO NOT drop requested SELECT projection columns.
- DO NOT arbitrarily convert MAX/MIN into ORDER BY + LIMIT 1.
- DO NOT inject CAST unless supported by column data evidence.
- Return ONLY the raw, repaired SQL string for {dialect}. Do NOT wrap in markdown or backticks. No conversational text."""

        return f"""You are MapleDoctor, an expert SQL Error Detection and Repair specialist following the MapleDoctor hybrid repair methodology.

{context_sec}

{error_sec}

{location_sec}

{exec_sec}

{repair_sec}

{constraints_sec}
"""
