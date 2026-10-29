# MapleDoctor Integration: SQL Error Detection & Repair Module

This document outlines the architecture, detection mechanics, repair rules, validation safeguards, and integration points of the **MapleDoctor** module in **CG-SQL (Concept-Grounded Multi-Agent SQL Synthesizer)**.

The implementation faithfully adheres to the research paper:
> **"Understanding, Detecting, and Repairing Real-World In-Context-Learning-Based Text-to-SQL Errors"**  
> by Jiawei Shen et al., *Proc. ACM Softw. Eng., FSE, 2026*.

---

## 1. Executive Summary & Core Philosophy

MapleDoctor is a post-generation detection and targeted repair layer designed to improve execution rates and semantic correctness without blindly regenerating SQL queries from scratch.

### The Rule-First Hybrid Repair Philosophy
1. **Detect the Error**: Extract symptoms from DBMS execution errors, AST anti-patterns, database schema facts, foreign-key relationships, and lightweight probes.
2. **Deterministic Rule Repair**: If a high-confidence deterministic repair rule exists (e.g., function hallucination, single-table column mismatch, unused alias, clear edit-distance typo, missing join with unique foreign-key path, implicit integer division, ascending sort with NULL), apply the rule **without calling an LLM**.
3. **Constrained LLM Fallback**: If the error is ambiguous (e.g., multiple candidate tables, multiple foreign-key paths) or requires semantic interpretation (value specification violations, aggregation/comparison misuse, suspicious execution symptoms), invoke a constrained LLM repairer with an error-specific 6-section prompt.
4. **Re-Execute & Validate**: Dynamically re-execute the repaired query against the target database engine, verify previous error resolution, and enforce mis-repair safety guards.
5. **Iterative Repair & Safe Termination**: If secondary errors remain, iteratively repair up to 3 attempts. If the query remains non-executable after repair attempts, **terminate the process and revert to the original query** as dictated by the paper's safety protocol.

---

## 2. Integration Point in the CG-SQL Architecture

MapleDoctor operates as a post-generation detection and repair layer that fits directly into the existing multi-agent blackboard flow without altering existing agents or API contracts:

```
Natural Language Question
        |
        v
QueryUnderstandingAgent (NLP Parsing & Concept Grounding)
        |
        v
SchemaGroundingAgent (Bidirectional Linking & E/R Reasoning)
        |
        v
SQLGenerationAgent (Candidate Generation: Full vs Pruned Schema)
        |
        v
Generated SQL Candidates
        |
        v
ValidationExecutionAgent (Static Validator & Database Execution)
        |
        +-----------------------------+
        |                             |
  Validation / Execution Error        Execution Succeeded
        |                             |
        v                             v
   RepairAgent                 RiskHedgingAgent (Multidimensional Scoring)
  (Powered by MAPLEDoctor)            |
        |                             v
Targeted Hybrid Repair            Final Output (API / UI)
        |
        v
Re-Execute / Validate
        |
        +-- Success -> Return Repaired SQL Candidate
        +-- Remains non-executable -> Revert to Original SQL
```

### Module File Layout (`src/mapledoctor/`)
- **`src/mapledoctor/models.py`**: Pydantic data models for error categories, locations, detection results, and repair history.
- **`src/mapledoctor/ast_utils.py`**: AST traversal, division/join/subquery/order-by inspection, and AST transforms using `sqlglot`.
- **`src/mapledoctor/probes.py`**: Safe, read-only lightweight database probes (Algorithm 1 value-overlap probe, NULL existence probe, subquery row-count probe, sample/distinct value probes).
- **`src/mapledoctor/detector/`**:
  - `dbms_detector.py`: Parses DBMS runtime errors and resolves schema mismatches.
  - `ast_detector.py`: Static AST anti-pattern detector.
  - `symptom_detector.py`: Identifies suspicious execution symptoms (EMPTY_RESULT, SINGLE_NULL_RESULT).
  - `detector.py`: `UniversalDetector` coordinating detection with Execution-First priority.
- **`src/mapledoctor/rules/`**: Implementations of all 11 paper rules (`rule1` through `rule11`).
- **`src/mapledoctor/prompts/repair_prompts.py`**: Error-specific 6-section constrained prompt builder.
- **`src/mapledoctor/repair/`**:
  - `rule_repairer.py`: Deterministic rule repair engine.
  - `llm_repairer.py`: Constrained LLM repairer.
  - `hybrid_repairer.py`: Rule-First hybrid coordinator.
- **`src/mapledoctor/validator/repair_validator.py`**: Post-repair validator with re-execution and mis-repair safety guards.
- **`src/mapledoctor/engine.py`**: `MapleDoctorEngine` orchestrating end-to-end detection, repair, validation, and safe termination.
- **`src/tools/maple_doctor.py`**: `MAPLEDoctorRepairer` exposing the full engine while preserving complete backwards compatibility with `RepairAgent`.

---

## 3. Detection & Repair Rules Taxonomy

| Rule # | Category | Detection Method | Repair Strategy |
|---|---|---|---|
| **Rule 1** | **Function Hallucination** | DBMS error (`no such function`) or AST scan for unsupported dialect functions. | Predefined, DBMS-aware alternative: `DIVIDE(a, b) -> a / b`, `YEAR(x) -> STRFTIME('%Y', x)`, `DATE_TRUNC -> STRFTIME`. |
| **Rule 2** | **Table-Column Mismatch** | DBMS error (`no such column`) where column exists in another table in schema. | If exactly 1 table contains column: replace table prefix deterministically. If multiple tables: LLM fallback. |
| **Rule 3** | **Unused Alias** | Query defines alias `T AS A`, but references `T.col` instead of `A.col`. | Replace original table reference with assigned alias: `T.col -> A.col`. |
| **Rule 4** | **Schema Hallucination** | Referenced column/table does not exist in schema. | Normalized Levenshtein edit distance. Single clear match (`customer_nmae -> customer_name`): deterministic. Ambiguous: LLM fallback. |
| **Rule 5** | **Missing JOIN** | Query references column in unjoined table. | Single foreign-key path in schema: add `JOIN unjoined ON fk = pk`. Multiple or no FK: LLM fallback. |
| **Rule 6** | **Implicit Type Conversion** | AST division node (`/`) where both operands are integers without `CAST`. | Wrap numerator in `CAST(... AS REAL)` (SQLite) or `CAST(... AS FLOAT)`. |
| **Rule 7** | **Using "=" instead of "IN"** | AST equality where RHS is a multi-row subquery or runtime subquery error. | Replace `=` with `IN` when detector proves RHS is a set: `col IN (subquery)`. |
| **Rule 8** | **Ascending Sort with NULL** | `ORDER BY col ASC` or `MIN(col)` where column contains NULLs (verified via probe). | Add `col IS NOT NULL` condition to WHERE clause, preserving existing filters. |
| **Rule 9** | **Comparing Unrelated Columns** | JOIN condition `L.col1 = R.col2` lacks FK relationship AND Algorithm 1 value-overlap probe returns 0 rows. | Search FK candidates between tables. Single FK candidate: deterministic replacement. Multiple: LLM fallback. |
| **Rule 10** | **Violating Value Specification** | WHERE predicate value violates known enum/distinct values (e.g. case mismatch). | LLM-assisted repair providing valid specification values for targeted mapping. |
| **Rule 11** | **Aggregation / Comparison Misuse** | `MAX/MIN/ORDER BY` on TEXT column containing numeric strings (lexicographical sorting). | LLM-assisted repair providing sample values and schema context (e.g., `MAX(CAST(speed AS REAL))`). |
| **Symptom 1** | **Empty Result Set** | Query returns 0 rows unexpectedly. | Suspicious signal proxy; error-specific LLM semantic repair with question context. |
| **Symptom 2** | **Single NULL Result** | Query returns `[[None]]`. | Suspicious signal proxy; error-specific LLM semantic repair with question context. |

*Note: Missing Quote is explicitly excluded from paper-derived MapleDoctor rules per section 4 of the paper.*

---

## 4. Error-Specific LLM Prompt Structure

When deterministic rules cannot resolve an issue, MapleDoctor constructs a structured prompt containing:
1. **CONTEXT**: Natural-language question, target DBMS dialect, allowed schema tables/columns, foreign keys, and failed SQL.
2. **ERROR DESCRIPTION**: Exact detected category, rule name, and diagnostic explanation.
3. **ERROR LOCATION**: Specific clause, table, column, operator, function, or predicate.
4. **EXECUTION INFORMATION**: Exact DBMS error message, runtime probe results, and execution symptoms.
5. **REPAIR INSTRUCTION**: Exact surgical repair strategy, candidates, and valid specification values.
6. **SAFETY CONSTRAINTS**: Strict preservation of intent, prohibition of schema/column invention, no projection dropping, and minimal necessary modification.

---

## 5. Mis-Repair Safety Guards

MapleDoctor actively tests and guards against the 9 failure patterns identified in the paper:
1. **Extremum Rewrite Guard**: Rejects converting `MAX(...)` or `MIN(...)` into `ORDER BY ... LIMIT 1`.
2. **Projection Drop Guard**: Prevents repairs from dropping requested SELECT columns.
3. **Schema Hallucination Guard**: Validates that all tables and columns in the repaired query exist in the database schema.
4. **CAST Injection Guard**: Prevents inserting `CAST` on text columns without empirical data evidence.
5. **Value Over-Correction Guard**: Protects correct constant literals from arbitrary replacement.
6. **Empty Symptom Over-Correction Guard**: Avoids corrupting valid queries that legitimately return 0 rows.
7. **Column Substitution Guard**: Ensures columns are not swapped for arbitrary alternatives.
8. **Predicate Flip Guard**: Protects negation (`NOT IN`, `NOT NULL`) and boolean structure.
9. **Rule-Based Over-Triggering Guard**: Requires strict multi-condition guards before applying deterministic rules.

---

## 6. How to Run the Tests

To execute all MapleDoctor test suites:

```bash
# Run all 50 tests (Rules, Scenarios, False Positives, Safety, Integration)
./venv/bin/pytest tests/ -v

# Run individual test modules
./venv/bin/pytest tests/test_mapledoctor_rules.py -v
./venv/bin/pytest tests/test_mapledoctor_symptoms_and_scenarios.py -v
./venv/bin/pytest tests/test_mapledoctor_false_positives.py -v
./venv/bin/pytest tests/test_mapledoctor_misrepair_safety.py -v
./venv/bin/pytest tests/test_integration_mapledoctor.py -v
```

---

## 7. Python API Usage

```python
from src.knowledge.core.knowledge_base import KnowledgeBase
from src.knowledge.core.repository import KnowledgeRepository
from src.mapledoctor.engine import MapleDoctorEngine

kb = KnowledgeBase(KnowledgeRepository())
engine = MapleDoctorEngine(kb=kb)

# Example: Repair an implicit integer division
result = engine.diagnose_and_repair(
    sql="SELECT COUNT(*) / 12 FROM department",
    question="What is the average number of departments per month?",
    dataset="spider",
    database_id="department_management",
    dialect="SQLite"
)

print(f"Repaired: {result.was_repaired}")
print(f"Final SQL: {result.final_sql}")
# Output: SELECT CAST(COUNT(*) AS REAL) / 12 FROM department
```
