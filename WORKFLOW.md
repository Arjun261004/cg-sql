# CG-SQL: End-to-End Multi-Agent Workflow & Architecture

This document provides a comprehensive, step-by-step walkthrough of how **CG-SQL (Concept-Grounded Multi-Agent SQL Synthesizer)** processes a natural language query into a validated, risk-hedged SQL query with MapleDoctor-powered empirical verification, diagnosis, and repair.

---

## 1. High-Level Architecture Overview

The system consists of **exactly six intelligent agents** coordinated dynamically via an evidence-driven **Decision Engine** and blackboard state (**`GraphState`**), anchored by a deterministic **Knowledge Base**:

```mermaid
flowchart TD
    User([User Prompt + Database ID]) --> API[FastAPI / Client / main.py]
    API --> Init[Initialize GraphState & KnowledgeBase]
    Init --> DE{Decision Engine<br/>Inspects Blackboard State}

    subgraph KB["Deterministic Knowledge Base Layer (src/knowledge/)"]
        K_BR[(business_rules/)]
        K_SC[(schemas/)]
        K_RE[(relationships/)]
        K_DI[(dialects/)]
        K_ST[(statistics/)]
    end

    subgraph A1["1. QueryUnderstandingAgent (src/agents/query_understanding_agent.py)"]
        T1["NLPIntentParser (src/tools/intent_parser.py)"]
        T2["ConceptGrounder (src/tools/concept_grounder.py)"]
    end

    subgraph A2["2. SchemaGroundingAgent (src/agents/schema_grounding_agent.py)"]
        T3["BidirectionalSchemaLinker (src/tools/schema_linker.py)"]
        T4["ERReasoner (src/tools/er_reasoner.py)"]
        T5["SchemaPruner (src/tools/schema_linker.py)"]
    end

    subgraph A3["3. SQLGenerationAgent (src/agents/sql_generation_agent.py)"]
        T6["QueryPlanner (src/tools/query_planner.py)"]
        T7["DialectResolver (src/tools/dialect_resolver.py)"]
        T8["SQLCritic (src/tools/sql_critic.py)"]
        T_FB["DeterministicFallback (_build_deterministic_sql)"]
    end

    subgraph A4["4. ValidationExecutionAgent (src/agents/validation_execution_agent.py)"]
        T9["StaticValidator & ErrorClassifier (src/tools/static_analyzer.py)"]
        T10["DatabaseExecutor (src/tools/database_executor.py)"]
        T11["SemanticVerifier (src/tools/semantic_verifier.py)"]
    end

    subgraph A5["5. RepairAgent (src/agents/repair_agent.py)"]
        T12["MapleDoctorEngine (src/mapledoctor/engine.py)"]
        T13["UniversalDetector (Rules 1-11 & Verification)"]
        T14["RuleRepairer (Rules 1-9 Deterministic AST)"]
        T15["LLMRepairer (Rules 10-11 Constrained Fallback)"]
    end

    subgraph A6["6. RiskHedgingAgent (src/agents/risk_hedging_agent.py)"]
        T16["RiskEvaluator (Multi-Factor Evidence Formula)"]
    end

    %% Dynamic transitions
    DE -->|Cycle 1: ActionType.UNDERSTAND_QUERY| A1
    A1 -->|state.concept_grounding| DE
    
    DE -->|Cycle 2: ActionType.GROUND_SCHEMA| A2
    A2 -->|state.schema_linking| DE

    DE -->|Cycle 3: ActionType.GENERATE_SQL| A3
    A3 -->|state.sql_candidates| DE

    DE -->|Cycle 4: ActionType.VALIDATE_EXECUTION| A4
    A4 -->|state.validation_result| DE
    
    DE -->|Cycle 5: ActionType.REPAIR_SQL| A5
    A5 -->|Branch 1: Execution Passed -> Verify Anti-patterns (mapledoctor_verified=True)| DE
    A5 -->|Branch 2: Unresolvable Schema Hallucination -> Catalog Diagnosis (conf=0.0)| DE
    A5 -->|Branch 3: Recoverable Error -> Patched SQL| A4
    
    DE -->|Cycle 6: ActionType.HEDGE_RISK| A6
    A6 -->|state.risk_evaluation, final_sql, final_confidence| DE
    
    DE -->|ActionType.FINALIZE| Final([Validated Response to User / Frontend UI])

    %% Knowledge Base Connections
    K_BR -.-> A1
    K_SC & K_RE -.-> A2
    K_DI -.-> A3
    K_SC & K_ST -.-> A4
    K_DI & K_SC -.-> A5
    K_RE & K_ST -.-> A6
```

---

## 2. Tools Inventory by Agent

All low-level algorithms, parsing logic, and execution routines reside in `src/tools/` and `src/mapledoctor/`, encapsulated by the six top-level agents:

| Agent | Tool Class | File Path | Primary Function |
|---|---|---|---|
| **`QueryUnderstandingAgent`** | `NLPIntentParser` | [`src/tools/intent_parser.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/intent_parser.py) | Extracts limits, sorting, aggregations, temporal constraints, and range filters (`BETWEEN`, comparison operators, string values). |
| | `ConceptGrounder` | [`src/tools/concept_grounder.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/concept_grounder.py) | Maps tokens to canonical business entities, metrics, dimensions, and glossary definitions with plural stemming. |
| **`SchemaGroundingAgent`** | `BidirectionalSchemaLinker` | [`src/tools/schema_linker.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/schema_linker.py) | **Forward Linking**: Query concepts $\to$ candidate tables/columns with plural stemming.<br/>**Backward Validation**: Candidate schema $\to$ expressible concepts vs. user intent. Emits schema objection if concepts are missing from DB. |
| | `ERReasoner` | [`src/tools/er_reasoner.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/er_reasoner.py) | Analyzes foreign key relationships, builds Steiner-tree minimal join graphs, and flags fan-out / chasm traps. |
| | `SchemaPruner` | [`src/tools/schema_linker.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/schema_linker.py) | Generates two distinct contexts: a minimal **pruned schema candidate** and a broad **full schema candidate**. |
| **`SQLGenerationAgent`** | `QueryPlanner` | [`src/tools/query_planner.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/query_planner.py) | Builds relational execution plans, step-by-step CTE breakdowns, and aggregation/filter placement. |
| | `DialectResolver` | [`src/tools/dialect_resolver.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/dialect_resolver.py) | Loads dialect syntax rules (SQLite, DuckDB, Snowflake, Postgres, BigQuery) from the Knowledge Base. |
| | `SQLCritic` | [`src/tools/sql_critic.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/sql_critic.py) | Pre-validation review for ambiguous aliases, missing group by keys, or unquoted string literals. |
| | `DeterministicFallback` | [`src/agents/sql_generation_agent.py`](file:///Users/arjuns/Desktop/sqlpro/src/agents/sql_generation_agent.py) | `_build_deterministic_sql()` builds valid SQL with parsed filters when LLM quotas are exhausted or offline. |
| **`ValidationExecutionAgent`**| `StaticValidator` & `ErrorClassifier` | [`src/tools/static_analyzer.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/static_analyzer.py) | Deterministic AST static checking; classifies syntax/schema errors into 11 formal error categories. |
| | `DatabaseExecutor` | [`src/tools/database_executor.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/database_executor.py) | Sandboxed SQLite and DuckDB query execution with strict timeouts and maximum row limits. |
| | `SemanticVerifier` | [`src/tools/semantic_verifier.py`](file:///Users/arjuns/Desktop/sqlpro/src/tools/semantic_verifier.py) | Inspects result sets for 0-row empty sets, Cartesian duplicate rows, and schema type alignment. |
| **`RepairAgent`** | `MapleDoctorEngine` | [`src/mapledoctor/engine.py`](file:///Users/arjuns/Desktop/sqlpro/src/mapledoctor/engine.py) | Unified engine implementing Shen et al. (FSE 2026): Rule-first detection and hybrid repair. |
| | `UniversalDetector` | [`src/mapledoctor/detector/universal.py`](file:///Users/arjuns/Desktop/sqlpro/src/mapledoctor/detector/universal.py) | Evaluates Rules 1-11 and verifies successful queries for silent logical/convention bugs. |
| | `RuleRepairer` | [`src/mapledoctor/repair/rule_repairer.py`](file:///Users/arjuns/Desktop/sqlpro/src/mapledoctor/repair/rule_repairer.py) | Deterministic AST repairs for Rules 1-9 (0 ms latency). |
| | `LLMRepairer` | [`src/mapledoctor/repair/llm_repairer.py`](file:///Users/arjuns/Desktop/sqlpro/src/mapledoctor/repair/llm_repairer.py) | 6-section constrained LLM fallback repair for Rules 10-11 with rollback guard. |
| **`RiskHedgingAgent`** | `RiskEvaluator` | [`src/agents/risk_hedging_agent.py`](file:///Users/arjuns/Desktop/sqlpro/src/agents/risk_hedging_agent.py) | Multi-factor evidence scoring function evaluating execution success, semantic checks, and simplicity. |

---

## 3. The Central Role of the Knowledge Base

The Knowledge Base (`src/knowledge/`) is a deterministic, offline-capable repository organized into structured stores:

```
src/knowledge/stores/
├── business_rules/   # Enterprise glossary, business definitions, KPI metric formulas
├── schemas/          # Database table catalogs, column data types, nullability, primary keys
├── relationships/    # Foreign key constraints, cardinalities (1:1, 1:N, M:N), join keys
├── dialects/         # Dialect quirks (date functions, identifier quotes, regex functions)
└── statistics/       # Table row counts, distinct value counts, nullability distributions
```

### Knowledge Base Access in the Workflow:
1. **At Step 1**: `QueryUnderstandingAgent` searches `business_rules/` and physical schemas to map business terms to canonical concepts.
2. **At Step 2**: `SchemaGroundingAgent` runs BM25 schema search on `schemas/` and queries `relationships/` to find valid foreign key join paths.
3. **At Step 3**: `SQLGenerationAgent` queries `dialects/` to format dialect-compliant syntax (e.g., `BETWEEN`, `STRFTIME`, quotes).
4. **At Step 4 & 5**: `ValidationExecutionAgent` and `RepairAgent` verify query structures against `schemas/` and resolve errors using `dialects/`. On schema mismatches, `RepairAgent` queries available tables to emit clear diagnostic guidance.
5. **At Step 6**: `RiskHedgingAgent` cross-references candidate tables against `relationships/` to penalize unnecessary joins.

---

## 4. Step-by-Step Lifecycle (From User Input to Response)

### Step 1: User Request & Initialization
1. The user submits a natural language question (e.g., *"show all pilots of age between 30 and 40"*) and selects a database (`aircraft.sqlite`).
2. `GraphState` is initialized on the blackboard with:
   - `original_request = "show all pilots of age between 30 and 40"`
   - `database = "aircraft"`
   - `db_path = "./spider_data/database/aircraft/aircraft.sqlite"`
   - `dialect = "SQLite"`
3. The `Orchestrator` invokes `DecisionEngine.decide_next_action()`, which returns `ActionType.UNDERSTAND_QUERY`.

---

### Step 2: `QueryUnderstandingAgent`
1. **Observe**: Receives `original_request`.
2. **Tools Executed**:
   - `NLPIntentParser`: Extracts range filter `filters = [{"field": "age", "op": "BETWEEN", "value": [30, 40]}]`.
   - `ConceptGrounder`: Applies dynamic schema discovery and plural stemming: `"pilots"` $\to$ entity `pilot`, `"age"` $\to$ metric `Age`.
3. **State Mutation**:
   - Stores `ConceptGroundingResult` on `state.concept_grounding`.
4. **Message Emitted**: Posts `MessageType.PROPOSAL` with capability tag `[Intent & Concept Grounding]`.
5. **Decision Engine**: Reads that `concept_grounding` is satisfied and determines next action: `ActionType.GROUND_SCHEMA`.

---

### Step 3: `SchemaGroundingAgent`
1. **Observe**: Reads `state.concept_grounding`.
2. **Tools Executed**:
   - `BidirectionalSchemaLinker (Forward)`: Searches `schemas/` for terms `"pilot"` and `"Age"`. Confirms table `pilot` and column `Age`.
   - `ERReasoner`: Searches `relationships/` for join paths. Single table `pilot` satisfies all intent components.
   - `BidirectionalSchemaLinker (Backward)`: Validates that table `pilot` fully satisfies the user intent:
     $$\text{Confidence}_{\text{backward}} = 1.00$$
   - *Schema Mismatch Branch*: If user asks for entities that do NOT exist in the database (e.g. `students` in `aircraft`), backward confidence drops to $0.10$ and an `OBJECTION` message is posted.
   - `SchemaPruner`: Generates a minimal pruned schema candidate (`pilot` only) and a full schema candidate (`pilot`, `aircraft`, `match`, `airport`, `airport_aircraft`).
3. **State Mutation**:
   - Stores `SchemaLinkingResult` on `state.schema_linking`.
4. **Message Emitted**: Posts `MessageType.PROPOSAL` (or `OBJECTION` if unmatched concepts exist).
5. **Decision Engine**: Determines next action: `ActionType.GENERATE_SQL`.

---

### Step 4: `SQLGenerationAgent`
1. **Observe**: Reads `state.concept_grounding` and `state.schema_linking`.
2. **Tools Executed**:
   - `DialectResolver`: Loads SQLite syntax rules from `dialects/sqlite.json`.
   - `QueryPlanner`: Builds relational plan: Scan `pilot` $\to$ Filter `Age BETWEEN 30 AND 40`.
   - `LLMClient`: Calls Gemini multi-model failover chain (`gemini-3.5-flash-lite` $\to$ `gemini-3.8-flash` $\to$ `gemini-3.6-flash`).
   - `DeterministicFallback`: If LLM quota is hit (429) or offline, `_build_deterministic_sql` compiles valid SQL preserving the `BETWEEN` filter: `SELECT * FROM pilot WHERE Age BETWEEN 30 AND 40`.
   - Refuses to hallucinate substitute tables if schema linking registered missing concepts (`SELECT * FROM students WHERE course = 'science'`).
   - Generates competing SQL candidates:
     - **Candidate A (`full_schema`)**: `SELECT * FROM pilot WHERE Age BETWEEN 30 AND 40`
     - **Candidate B (`pruned_schema`)**: `SELECT * FROM pilot WHERE Age BETWEEN 30 AND 40`
3. **State Mutation**:
   - Appends candidates to `state.sql_candidates`.
4. **Message Emitted**: Posts `MessageType.PROPOSAL` with capability tag `[Multi-Candidate Planning & Dialect Synthesis]`.
5. **Decision Engine**: Determines next action: `ActionType.VALIDATE_EXECUTION`.

---

### Step 5: `ValidationExecutionAgent`
1. **Observe**: Reads active candidate from `state.sql_candidates`.
2. **Tools Executed**:
   - `StaticValidator`: Parses SQL syntax and performs AST validation via `sqlglot`.
   - `DatabaseExecutor`: Executes query against `aircraft.sqlite` in a sandboxed connection.
   - `SemanticVerifier`: Inspects result set:
     - Non-empty (returns 5 rows).
     - No Cartesian explosion or duplicate rows.
3. **State Mutation**:
   - Stores `ValidationResult` on `state.validation_result` (`execution_success = True`, `row_count = 5`).
4. **Decision Engine**: Determines next action: `ActionType.REPAIR_SQL`.

---

### Step 6: `RepairAgent` (MapleDoctor Engine — Verification, Diagnosis & Repair)
The `RepairAgent` is ALWAYS evaluated by the Decision Engine:

1. **Path A: Universal Verification (Execution Succeeded)**:
   - `UniversalDetector` verifies that the successful query does not contain silent anti-patterns from the paper's 11 error rules.
   - Sets `state.mapledoctor_verified = True`.
   - Posts `MessageType.EVIDENCE`: `"MAPLEDoctor verified: No syntax, schema, logic, or convention anti-patterns detected."`
   - UI status: `RepairAgent` is highlighted in **Emerald Green**!

2. **Path B: Schema Mismatch Diagnosis (Unresolvable Schema Hallucination)**:
   - If error is `SCHEMA_MISSING` (e.g. `no such table: students`), recognizes that the requested entity is absent from the selected database.
   - Bypasses fruitless LLM repairs to save quota.
   - Queries `KnowledgeBase` for available tables in the database.
   - Posts `MessageType.OBJECTION`: `"MapleDoctor Diagnosis: The requested attributes/entities do not exist in database 'aircraft'. Available tables in 'aircraft': ['pilot', 'aircraft', 'match', 'airport', 'airport_aircraft']."`
   - Sets `state.final_answer = "Schema Error: The requested attributes or entities do not exist in database 'aircraft'. Available tables: pilot, aircraft, match, airport, airport_aircraft."`.
   - Sets `state.mapledoctor_verified = True`.
   - UI status: `RepairAgent` is highlighted in **Amber Warning**!

3. **Path C: Empirical Self-Repair (Recoverable Syntax / Logic Error)**:
   - **Rules 1–9**: Applies instant deterministic AST patches (function hallucinations, alias errors, column mismatches, missing joins, type casts, NULL sorting).
   - **Rules 10–11**: Applies 6-section constrained LLM repair.
   - **Safety Rollback Guard**: Validates repaired SQL against 9 mis-repair failure modes; rolls back if repair causes regressions.
   - Routes **back to `ValidationExecutionAgent`** to re-verify the repaired query.

4. **Decision Engine**: Proceeds to `ActionType.HEDGE_RISK`.

---

### Step 7: `RiskHedgingAgent`
1. **Observe**: Reads candidate queries and execution/diagnosis results.
2. **Tools Executed**:
   - `RiskEvaluator`: Evaluates candidates using multi-factor evidence scoring:
     $$\text{Score} = \text{Exec Success } (+0.50) + \text{Semantic Passed } (+0.30) + \text{Pruned Simplicity } (+0.10) + \text{Non-Empty } (+0.10) - \text{Join Penalty } (-0.15) - \text{Duplicates } (-0.20)$$
   - **On Success**: Score = 1.00 $\to$ elects Candidate B as winning query, sets `state.final_sql` and `state.final_confidence = 1.0`.
   - **On Schema Error**: Execution failed $\to$ sets `state.final_confidence = 0.0`, preserves diagnostic `final_answer`.
3. **State Mutation**:
   - Sets `state.risk_evaluation` and `state.final_confidence`.
4. **Decision Engine**: Yields `ActionType.FINALIZE`.

---

### Step 8: Return Payload to Client & UI Rendering
The API formats and returns the complete execution bundle:
```json
{
  "request_id": "3bb904f2-9939-4204-a0c0-bdd32b0d6193",
  "status": "completed",
  "sql": "SELECT * FROM pilot WHERE Age BETWEEN 30 AND 40",
  "confidence": 1.0,
  "answer": "Validated SQL successfully (5 rows returned).",
  "execution_data": [
    {"Pilot_Id": 5, "Name": "Ellen Ledner III", "Age": 31},
    {"Pilot_Id": 6, "Name": "Elisha Hickle V", "Age": 37},
    {"Pilot_Id": 8, "Name": "Winnifred Boyle", "Age": 30},
    {"Pilot_Id": 11, "Name": "Blaise Muller", "Age": 33},
    {"Pilot_Id": 12, "Name": "Baylee Steuber", "Age": 30}
  ],
  "risk_evaluation": {
    "selected_candidate_id": "cand_b_pruned",
    "selected_candidate_type": "pruned",
    "hedging_strategy": "evidence_confidence_and_simplicity",
    "risk_factors": [
      "+0.50 Execution succeeded",
      "+0.30 Semantic verification passed",
      "+0.10 Pruned minimal schema (lower surface area)",
      "+0.10 Non-empty result set returned"
    ],
    "confidence": 1.0
  }
}
```

In the React UI (`frontend/src/App.tsx`), all six agents are dynamically displayed with their status cards, timeline traces, SQL diffs, and query results.
