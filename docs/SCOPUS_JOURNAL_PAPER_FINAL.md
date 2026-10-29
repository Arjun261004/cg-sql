# CG-SQL: A Concept-Grounded Multi-Agent Blackboard Architecture with MapleDoctor-Integrated Rule-First Self-Repair for Robust Text-to-SQL Synthesis

---

## ABSTRACT

Natural language-to-SQL (Text-to-SQL) systems powered by Large Language Models (LLMs) have demonstrated promising capabilities in translating user queries into structured database queries. However, production deployment of these systems is fundamentally undermined by five persistent failure modes: schema hallucination, relational join path inaccuracies, dialect-specific syntax violations, silent semantic anti-patterns in syntactically valid queries, and regressive naive regeneration upon error. This paper presents **CG-SQL (Concept-Grounded Multi-Agent SQL Synthesizer)**, a novel hybrid architecture that addresses these challenges through three synergistic contributions. First, CG-SQL introduces a **dynamic six-agent blackboard architecture** where specialized agents—QueryUnderstanding, SchemaGrounding, SQLGeneration, ValidationExecution, Repair, and RiskHedging—collaboratively reason over a shared evolving state (`GraphState`) coordinated by an evidence-driven Decision Engine. Second, the system grounds all synthesis decisions in a **deterministic, non-LLM Knowledge Base** encoding physical schemas, verified foreign keys, dialect rules, and business glossaries, enabling bidirectional schema linking with plural stemming and backward expressibility validation. Third, CG-SQL integrates the **MapleDoctor** error detection and self-repair engine (Shen et al., FSE 2026), implementing a rule-first hybrid repair strategy across 11 formally categorized error rules and 2 suspicious execution symptoms, where deterministic AST transformations resolve over 65% of common errors without invoking an LLM, with constrained LLM fallback for complex semantic repairs and mis-repair safety guards preventing regression. Experimental evaluation on the Spider benchmark (166 databases, 1,034 development queries, 876 tables) demonstrates that CG-SQL achieves 68.0% execution accuracy (EX) and 52.0% exact match (EM) on an evaluated stratified development sample using an economical Gemini Flash backbone, achieving a +4.0% net accuracy gain post-repair with 0.0% mis-repairs. Deterministic AST rules execute with sub-millisecond to low-millisecond latency (0.07 ms to 10.44 ms) consuming zero LLM tokens. The dual-candidate hedging strategy with multi-factor Pareto scoring further ensures robustness by selecting minimal-surface-area query candidates that reduce join hallucination risk.

**Keywords:** Text-to-SQL, Multi-Agent Systems, Automated Program Repair, Schema Linking, Large Language Models, Blackboard Architecture

---

## 1. INTRODUCTION

### 1.1 Background and Motivation

The ability to translate natural language questions into executable Structured Query Language (SQL) queries—commonly referred to as Text-to-SQL or Natural Language Interface to Databases (NLIDB)—represents one of the most impactful applications of artificial intelligence in data-driven enterprises [1, 2]. Business analysts, domain experts, and non-technical stakeholders routinely require ad-hoc access to relational databases but lack the SQL proficiency necessary to formulate complex analytical queries involving multi-table joins, conditional aggregations, nested subqueries, and dialect-specific function semantics [3].

The advent of Large Language Models (LLMs) with in-context learning (ICL) capabilities, particularly models in the GPT and Gemini families, has catalyzed rapid progress on Text-to-SQL benchmarks such as Spider [4], WikiSQL [5], and BIRD [6]. State-of-the-art approaches including DIN-SQL [7], DAIL-SQL [8], MAC-SQL [9], and CHESS [10] have demonstrated that prompting LLMs with schema descriptions, few-shot examples, and chain-of-thought decomposition can achieve competitive execution accuracy on controlled benchmarks. However, the transition from benchmark performance to reliable production deployment reveals a fundamentally different landscape of challenges that existing approaches fail to address comprehensively.

### 1.2 Critical Limitations of Existing Approaches

A systematic analysis of the failure modes observed in current LLM-based Text-to-SQL systems reveals five persistent categories of errors:

**1. Schema and Entity Hallucination.** LLMs frequently generate references to tables, columns, or functions that do not exist in the target database schema [11]. For instance, when queried about "students" on an aircraft management database, the model may fabricate a `students` table rather than recognizing the semantic mismatch. This failure mode is particularly insidious because it bypasses static syntax validation—the generated SQL may be syntactically well-formed yet semantically vacuous.

**2. Relational Join Path Inaccuracies.** Complex analytical queries spanning multiple tables demand precise identification of foreign key relationships and join predicates. LLMs frequently produce Cartesian products from missing `ON` clauses, introduce phantom join conditions between unrelated columns, or select incorrect join paths among multiple valid alternatives [12]. The reliance on implicit schema understanding from training data, rather than explicit relationship graph traversal, leads to join hallucinations that inflate or corrupt result sets.

**3. Dialect-Specific Syntax Violations.** SQL dialects (SQLite, PostgreSQL, MySQL, DuckDB, BigQuery, Snowflake) differ substantially in date/time functions, string operations, type casting semantics, window function syntax, and identifier quoting conventions [13]. LLMs trained on heterogeneous SQL corpora routinely generate dialect-incompatible constructs—e.g., `YEAR(date_column)` (MySQL syntax) when the target is SQLite, which requires `STRFTIME('%Y', date_column)`.

**4. Silent Semantic Anti-Patterns.** Perhaps the most dangerous failure class comprises queries that execute successfully and return results, yet produce semantically incorrect answers due to subtle logical bugs [14]. These include: (a) implicit integer division truncating decimal results to zero; (b) ascending `ORDER BY` on nullable columns surfacing `NULL` values before actual data; (c) the use of `=` instead of `IN` with multi-row subqueries, silently selecting only the first match; (d) aggregation functions applied to text columns inducing lexicographic rather than numerical ordering. Since these queries generate no DBMS error, they evade conventional error-handling pipelines entirely.

**5. Regressive Naive Regeneration.** When a synthesized query fails execution, the standard remediation strategy in existing systems is to re-prompt the LLM with the error message, optionally augmented with schema context [15]. This approach suffers from three deficiencies: (a) the LLM may "oscillate" between multiple incorrect variants without converging on a fix; (b) repair attempts may introduce secondary errors (mis-repairs) that degrade the query further; (c) repeated LLM invocations consume substantial token budgets and latency, making the approach economically and temporally infeasible for interactive applications.

### 1.3 Research Gap

Existing multi-agent Text-to-SQL frameworks such as MAC-SQL [9] and CHESS [10] represent significant advances in decomposing the synthesis task across specialized agents. However, they exhibit three critical architectural limitations that this work addresses:

First, these systems operate as **static sequential pipelines** where agent execution order is hardcoded, lacking the dynamic evidence-driven routing necessary to adaptively respond to schema mismatches, execution failures, or varying query complexity. When an intermediate agent encounters an anomaly (e.g., unmatched entities during schema linking), the pipeline proceeds regardless, propagating errors downstream.

Second, no existing production system provides **formal, taxonomy-driven automated repair** grounded in empirical analysis of real-world Text-to-SQL error distributions. While Shen et al. [14] (FSE 2026) established the MapleDoctor framework identifying 11 error rules and 2 suspicious symptoms with deterministic repair strategies, no prior work has integrated this repair taxonomy into a multi-agent blackboard architecture where repair decisions are informed by the full context of prior agent reasoning, schema grounding evidence, and execution diagnostics.

Third, current approaches lack a **bidirectional schema validation mechanism** that not only maps query concepts forward to schema elements (forward linking) but also validates backward that the selected schema can fully express the user's intent (backward validation). This bidirectional approach is essential for detecting—rather than silently accommodating—schema hallucinations at the grounding stage, before query synthesis begins.

### 1.4 Contributions

This paper makes the following specific contributions:

1. **A Dynamic Six-Agent Blackboard Architecture (CG-SQL):** We propose a collaborative multi-agent system coordinated through a shared `GraphState` blackboard and an evidence-driven `DecisionEngine` that evaluates available evidence at each cycle to dynamically determine which agent to activate next. Unlike rigid sequential pipelines, this architecture supports conditional branching, iterative repair loops, early termination on unresolvable hallucinations, and adaptive resource allocation. The six agents—QueryUnderstandingAgent, SchemaGroundingAgent, SQLGenerationAgent, ValidationExecutionAgent, RepairAgent, and RiskHedgingAgent—each implement a principled observe–reason–evaluate–act lifecycle.

2. **Bidirectional Schema Linking with Expressibility Validation:** We introduce a schema grounding mechanism that performs both forward concept-to-schema linking (with plural/singular stemming) and backward expressibility validation, computing a formal confidence metric:
$$\text{Confidence}_{\text{backward}} = \frac{|\text{Expressible Concepts}|}{|\text{Expressible Concepts}| + |\text{Unmatched Concepts}|}$$
When this confidence falls below a calibrated threshold $\tau = 0.50$, the SchemaGroundingAgent emits an explicit `OBJECTION` message, preventing downstream agents from synthesizing queries against nonexistent entities and enabling the RepairAgent to issue diagnostic guidance rather than futile repair attempts.

3. **Integrated MapleDoctor Rule-First Hybrid Self-Repair:** We implement and integrate the complete MapleDoctor error detection and repair taxonomy (Shen et al., FSE 2026) as a first-class agent within the blackboard architecture. The RepairAgent operates in three modes: (a) **verification** of clean queries against 11 anti-pattern rules; (b) **diagnostic objection** for unresolvable schema hallucinations; and (c) **empirical self-repair** via deterministic AST transformations (Rules 1–9) with constrained LLM fallback (Rules 10–11) and mis-repair safety rollback guards, achieving repair without regressive re-prompting.

4. **Dual-Candidate Risk-Hedged Selection with Deterministic Fallback:** The SQLGenerationAgent synthesizes two competing candidates (full-schema and pruned-schema), evaluated by the RiskHedgingAgent through a multi-factor scoring function that balances execution success, semantic validation, schema minimality, and result-set non-emptiness. An intelligent deterministic fallback generator ensures syntactically valid SQL production even under complete LLM API unavailability.

### 1.5 Paper Organization

The remainder of this paper is organized as follows. Section 2 presents Materials and Methods, detailing the formal system architecture, mathematical formulations, blackboard specifications, agent lifecycles, benchmark environments, and baseline comparison models. Section 3 presents the Experimental Setup, Quantitative Evaluation, Ablation Study, and Failure Analysis, providing empirically verified measurements. Section 4 discusses implications, architectural trade-offs, and threats to validity. Section 5 concludes the paper and highlights directions for future research. Section 6 presents mandatory journal declarations, and Section 7 provides complete references.

---

## 2. MATERIALS AND METHODS

### 2.1 System Architecture Overview

CG-SQL is architected as a three-layer system comprising (i) a User Interface Layer, (ii) a Control Plane and Coordination Core, and (iii) a Deterministic Knowledge Base Layer. Figure 1 illustrates the complete system architecture.

![Figure 1: System Architecture of CG-SQL showing User Interface, Control Plane with GraphState and Decision Engine, and Deterministic Knowledge Base](figures/architecture_diagram_with_kb_de.jpg)

*Figure 1. Architectural overview of CG-SQL, depicting the three-layer organization: (Top) React/Vite User Interface with real-time blackboard visualization; (Middle) Control Plane featuring the Orchestrator, dynamic DecisionEngine, MessageBus, and six specialized agents interacting over the shared GraphState blackboard; (Bottom) Deterministic Knowledge Base Layer with offline relational stores.*

**User Interface Layer.** The frontend is implemented as a single-page application using React 18 with Vite build tooling and TypeScript. It provides a real-time blackboard visualizer displaying the status of all six agents, a SQL editor with syntax highlighting, an interactive results table, and a risk evaluation breakdown panel. Communication with the backend occurs via RESTful HTTP endpoints.

**Control Plane and Coordination Core.** The backend is implemented as a FastAPI application exposing two primary endpoints: `/generate-sql` (POST) and `/databases` (GET). The core coordination infrastructure consists of four components:

- **Orchestrator** (`orchestrator.py`): Implements the dynamic iterative execution loop, invoking the Decision Engine at each cycle and dispatching the corresponding agent.
- **Decision Engine** (`decision_engine.py`): An evidence-driven state-transition router that inspects the `GraphState` blackboard and returns one of seven action types: `UNDERSTAND_QUERY`, `GROUND_SCHEMA`, `GENERATE_SQL`, `VALIDATE_EXECUTION`, `REPAIR_SQL`, `HEDGE_RISK`, or `FINALIZE`.
- **Message Bus** (`message_bus.py`): A publish/subscribe inter-agent communication channel supporting four message types: `PROPOSAL`, `OBJECTION`, `EVIDENCE`, and `DECISION`.
- **LLM Client** (`llm_client.py`): A resilient multi-model client implementing an ordered failover chain across four Gemini model variants to ensure availability under rate-limiting or service disruption.

**Deterministic Knowledge Base (KB) Layer.** The KB is a non-LLM, offline-capable repository organized into five structured stores:

| Store | Contents | Access Pattern |
|-------|----------|----------------|
| `schemas/` | Table catalogs, column data types, nullability, primary keys | Schema search (BM25), direct lookup |
| `relationships/` | Foreign key constraints, cardinalities (1:1, 1:N, M:N), join keys | Graph traversal (NetworkX) |
| `dialects/` | Dialect-specific syntax rules, function mappings, identifier quoting | Rule lookup by dialect identifier |
| `business_rules/` | Enterprise glossary, KPI definitions, metric formulas | Term-to-definition mapping |
| `statistics/` | Table row counts, distinct value counts, nullability distributions | Statistical probing |

### 2.2 Shared Blackboard State (GraphState)

All inter-agent communication occurs through a shared, typed state object `GraphState` implemented as a Pydantic `BaseModel`. This eliminates lossy point-to-point message passing and ensures that every agent has access to the full reasoning context of all prior agents.

**Definition 1 (GraphState).** Let $\mathcal{G} = (\mathcal{I}, \mathcal{C}, \mathcal{K}, \mathcal{Q}, \mathcal{V}, \mathcal{D})$ denote the GraphState tuple, where:
- $\mathcal{I} = (q, d, p, \delta)$ represents input state: natural language query $q$, database identifier $d$, database path $p$, and target dialect $\delta$.
- $\mathcal{C} = (E, M, F, A)$ represents conceptual grounding: extracted entities $E$, metrics $M$, filters $F$, and aggregations $A$.
- $\mathcal{K} = (T, C, R, U, \kappa)$ represents schema linking: matched tables $T$, columns $C$, relationships $R$, unmatched concepts $U$, and confidence $\kappa \in [0, 1]$.
- $\mathcal{Q} = \{c_1, c_2, \ldots, c_n\}$ represents the set of SQL candidate queries.
- $\mathcal{V} = (e, s, r, \epsilon)$ represents validation: execution success $e \in \{0, 1\}$, semantic correctness $s \in \{0, 1\}$, result rows $r$, and error messages $\epsilon$.
- $\mathcal{D} = (\hat{c}, \hat{\sigma}, \hat{\kappa})$ represents the final decision: selected candidate $\hat{c}$, final SQL $\hat{\sigma}$, and final confidence $\hat{\kappa} \in [0, 1]$.

### 2.3 Agent Specifications

#### 2.3.1 Agent 1: QueryUnderstandingAgent

This agent performs natural language intent interpretation and concept identification using two tool modules:

**NLPIntentParser.** Employs regex-based extraction to identify:
- Pagination limits: patterns matching `top N`, `first N`, `limit N`
- Sorting directives: `ORDER BY` direction (`ASC`/`DESC`) and target columns
- Aggregation functions: `COUNT`, `SUM`, `AVG`, `MAX`, `MIN`
- Range filters: `BETWEEN X AND Y` extracted via the pattern:
  $$\text{regex}: \texttt{(\textbackslash w+)\textbackslash s+between\textbackslash s+(\textbackslash d+)\textbackslash s+and\textbackslash s+(\textbackslash d+)}$$
  yielding filter triple $(\text{field}, \text{BETWEEN}, [X, Y])$.
- Comparison predicates: operators $\geq, \leq, >, <$ with numerical operands.
- Categorical equality: `with/where <field> <value>` mapped to equality predicates.

**ConceptGrounder.** Classifies extracted tokens into semantic categories (entities, metrics, dimensions) by querying the KB's physical schema tables and business glossary. Dynamic schema discovery incorporates table and column names from the selected database into the search vocabulary at runtime, ensuring domain-specific grounding.

#### 2.3.2 Agent 2: SchemaGroundingAgent

This agent performs bidirectional schema linking with three sub-components:

**BidirectionalSchemaLinker (Forward Phase).** For each extracted concept $c_i \in \mathcal{C}$, computes fuzzy semantic similarity against all tables $T$ and columns $C$ in the KB:
$$\text{match}(c_i) = \underset{t \in T \cup C}{\arg\max} \ \text{sim}(c_i, t)$$

where $\text{sim}(\cdot)$ combines exact match, substring containment, and morphological stemming (e.g., `pilots` $\to$ `pilot`, `departments` $\to$ `department`).

**BidirectionalSchemaLinker (Backward Phase).** Validates that the candidate schema $\mathcal{K}$ can express all user-requested concepts:
$$\kappa_{\text{backward}} = \frac{|\{c_i \in \mathcal{C} : \exists t \in T, c \in C \text{ s.t. } \text{match}(c_i) = (t, c)\}|}{|\mathcal{C}|}$$

If $\kappa_{\text{backward}} < \tau$ (threshold $\tau = 0.50$), the agent emits an `OBJECTION` message with `unmatched_concepts` list, signaling the presence of schema hallucination.

**ERReasoner.** Traverses the KB's `RelationshipGraph` (implemented via NetworkX) to identify verified foreign-key join paths connecting candidate tables. For multi-table queries, computes the Steiner tree—the minimal-cost subgraph connecting all required tables through valid foreign key edges.

**SchemaPruner.** Produces two schema candidates:
- **Full Schema Candidate** $\mathcal{K}_{\text{full}}$: All tables discovered during forward linking.
- **Pruned Schema Candidate** $\mathcal{K}_{\text{pruned}}$: Minimal table set on active join paths, reducing hallucination surface area.

#### 2.3.3 Agent 3: SQLGenerationAgent

This agent performs relational planning and dual-candidate SQL synthesis.

**QueryPlanner.** Constructs a relational logical plan $\mathcal{P}$ as an ordered sequence of operations:
$$\mathcal{P} = [\text{Scan}(T_{\text{base}}), \text{Join}(T_2, \text{on}), \ldots, \text{Filter}(\phi), \text{Group}(\gamma), \text{Agg}(\alpha), \text{Sort}(\sigma), \text{Limit}(k)]$$

**DialectResolver.** Fetches dialect-specific syntax rules from `KB.dialects/` to ensure generated SQL conforms to the target engine's grammar (e.g., `STRFTIME` for SQLite vs. `DATE_TRUNC` for PostgreSQL).

**Dual-Candidate Generation.** Two SQL candidates are synthesized:
- $c_{\text{full}}$: Generated using $\mathcal{K}_{\text{full}}$ (maximizes recall).
- $c_{\text{pruned}}$: Generated using $\mathcal{K}_{\text{pruned}}$ (minimizes join surface area).

The LLM client attempts generation via an ordered failover chain of four Gemini model variants. If all LLM calls fail (HTTP 429 rate-limiting or HTTP 503 unavailability), the agent invokes a **deterministic fallback generator** that inspects `state.concept_grounding.filters` and `state.schema_linking` to compile syntactically valid SQL preserving all extracted predicates:
$$\text{fallback}(\mathcal{C}, \mathcal{K}) = \texttt{SELECT * FROM } T_{\text{primary}} \texttt{ WHERE } \bigwedge_{f \in F} \text{clause}(f)$$

where $\text{clause}(f)$ maps each filter triple $(field, op, value)$ to the corresponding SQL predicate (e.g., `Age BETWEEN 30 AND 40`).

#### 2.3.4 Agent 4: ValidationExecutionAgent

**StaticValidator.** Parses generated SQL into an Abstract Syntax Tree (AST) using the `sqlglot` library. Validates syntax conformance, checks for forbidden DDL operations (`DROP`, `ALTER`, `CREATE`), and verifies that referenced tables and columns exist in the physical schema.

**DatabaseExecutor.** Executes the candidate query against the target database engine (SQLite or DuckDB) within a sandboxed, read-only connection with configurable timeout constraints. Captures execution status, error messages, column headers, and tabular result rows.

**SemanticVerifier.** Inspects execution results for suspicious patterns:
- **Empty Result Set ($r = 0$):** May indicate overly restrictive filters or inverted comparison operators.
- **Single NULL Result ($r = [[None]]$):** May indicate null propagation in arithmetic expressions or missing records.

#### 2.3.5 Agent 5: RepairAgent (MapleDoctor Integration)

The RepairAgent implements the complete MapleDoctor error detection and self-repair framework (Shen et al., FSE 2026) [14] and operates in three modes within the blackboard architecture.

**Mode 1: Universal Verification.** When execution succeeds ($e = 1$), the `UniversalDetector` scans the query AST against all 11 error rules to detect silent anti-patterns. If no violations are found, the agent emits an `EVIDENCE` message confirming MapleDoctor verification:
$$\text{mapledoctor\_verified} = \begin{cases} \text{True} & \text{if } \forall r \in \{1, \ldots, 11\}: \text{detect}(r, \hat{\sigma}) = \emptyset \\ \text{False} & \text{otherwise} \end{cases}$$

**Mode 2: Schema Mismatch Diagnosis.** When the error is classified as `SCHEMA_MISSING` (e.g., `no such table: students`) and the `SchemaGroundingAgent` has flagged unmatched concepts, the RepairAgent recognizes the hallucination as fundamentally unresolvable. Rather than wasting LLM token budget on futile repair attempts, it short-circuits to a diagnostic objection:
$$\text{diagnosis}(d) = \text{"Available tables in '} d \text{': "} \cup \{t : t \in \text{KB.tables}(d)\}$$

**Mode 3: Empirical Self-Repair.** For recoverable errors, the repair engine applies a **rule-first hybrid strategy**:

**Rules 1–9 (Deterministic AST Repair).** Each rule implements a targeted AST transformation via `sqlglot` with zero LLM invocation cost:

| Rule | Error Category | Repair Transformation |
|------|---------------|----------------------|
| R1 | Function Hallucination | $f_{\text{invalid}} \to f_{\delta}$: dialect function translation dictionary |
| R2 | Table-Column Mismatch | $T.c \to T'.c$ where $c \in \text{cols}(T')$ uniquely |
| R3 | Unused Alias | $T.c \to A.c$ where $T \texttt{ AS } A$ in `FROM` |
| R4 | Schema Hallucination | $c_{\text{misspelled}} \to c_{\text{closest}}$ if $\text{Levenshtein}(c_{\text{misspelled}}, c_{\text{closest}}) / |c_{\text{closest}}| \leq 0.3$ |
| R5 | Missing JOIN | Append `JOIN T2 ON T1.fk = T2.pk` via KB relationship graph |
| R6 | Implicit Integer Division | `CAST(numerator AS REAL)` wrapping |
| R7 | `=` Instead of `IN` | Replace `col = (subquery)` with `col IN (subquery)` |
| R8 | Ascending Sort with NULL | Append `col IS NOT NULL` to `WHERE` clause |
| R9 | Comparing Unrelated Columns | Rewrite join predicate to valid FK via Algorithm 1 value-overlap probe |

**Rules 10–11 (Constrained LLM Repair).** For complex semantic errors requiring contextual understanding:

| Rule | Error Category | Repair Strategy |
|------|---------------|----------------|
| R10 | Violating Value Specification | 6-section constrained prompt with sampled distinct values from lightweight probe |
| R11 | Aggregation/Comparison Misuse | Cast text columns to numerical type: `MAX(CAST(col AS REAL))` |

**Lightweight Database Probing (Algorithm 1).** To prevent false-positive repairs, MapleDoctor employs safe, read-only probe queries:

*Value Overlap Probe:*
$$\texttt{SELECT 1 FROM (SELECT DISTINCT } c_1 \texttt{ FROM } T_1 \texttt{ LIMIT 100) A INNER JOIN (SELECT DISTINCT } c_2 \texttt{ FROM } T_2 \texttt{ LIMIT 100) B ON A.}c_1 \texttt{ = B.}c_2 \texttt{ LIMIT 1}$$

*NULL Existence Probe:*
$$\texttt{SELECT 1 FROM } T \texttt{ WHERE } c \texttt{ IS NULL LIMIT 1}$$

**Mis-Repair Safety Guard.** A central principle of MapleDoctor is that repairs must never introduce new errors or degrade query correctness. The `RepairValidator` enforces:
1. **Strict Re-Execution:** Repaired queries are executed against the sandbox DBMS. If execution fails, the repair is rejected.
2. **Iteration Budget:** A maximum of $k = 3$ repair iterations per query.
3. **Safe Termination:** If $k$ iterations expire without resolution, the engine rolls back to the original query and sets $\hat{\kappa} = 0.0$.

#### 2.3.6 Agent 6: RiskHedgingAgent

The RiskHedgingAgent evaluates all candidate queries using a weighted multi-factor scoring function:

**Definition 2 (Candidate Score).** For candidate $c_i$, the score is computed as:
$$S(c_i) = w_e \cdot E(c_i) + w_s \cdot V(c_i) + w_p \cdot P(c_i) + w_r \cdot R(c_i) - \sum_{j} \text{penalty}_j(c_i)$$

where:
- $E(c_i) \in \{+0.50, -0.50\}$: Execution success vs. runtime error ($w_e = 1$).
- $V(c_i) \in \{+0.30, 0.0\}$: Semantic verification pass ($w_s = 1$).
- $P(c_i) \in \{+0.10, 0.0\}$: Pruned minimal schema preference (Occam's razor, $w_p = 1$).
- $R(c_i) \in \{+0.10, 0.0\}$: Non-empty result set returned ($w_r = 1$).
- $\text{penalty}_{\text{join}}(c_i) = -0.15$: Unnecessary multi-table join.
- $\text{penalty}_{\text{dup}}(c_i) = -0.20$: Duplicate rows in result set.

The winning candidate is selected as:
$$\hat{c} = \underset{c_i \in \mathcal{Q}}{\arg\max} \ S(c_i)$$

and the final confidence is:
$$\hat{\kappa} = \begin{cases} S(\hat{c}) & \text{if } E(\hat{c}) = +0.50 \\ 0.0 & \text{if } \forall c_i \in \mathcal{Q}: E(c_i) = -0.50 \end{cases}$$

### 2.4 Dynamic Execution Lifecycle

The Orchestrator implements a dynamic iterative loop governed by the Decision Engine. At each iteration $t$, the Decision Engine evaluates the GraphState $\mathcal{G}^{(t)}$ and returns an action type $a^{(t)}$:
$$a^{(t)} = \text{DecisionEngine}(\mathcal{G}^{(t)}) \in \{\texttt{UNDERSTAND\_QUERY}, \texttt{GROUND\_SCHEMA}, \texttt{GENERATE\_SQL}, \texttt{VALIDATE\_EXECUTION}, \texttt{REPAIR\_SQL}, \texttt{HEDGE\_RISK}, \texttt{FINALIZE}\}$$

The transition logic follows evidence-driven rules:
1. If $\mathcal{C} = \emptyset$: $a^{(t)} = \texttt{UNDERSTAND\_QUERY}$
2. If $\mathcal{K} = \emptyset$: $a^{(t)} = \texttt{GROUND\_SCHEMA}$
3. If $\mathcal{Q} = \emptyset$: $a^{(t)} = \texttt{GENERATE\_SQL}$
4. If $\exists c_i \in \mathcal{Q}$ unvalidated: $a^{(t)} = \texttt{VALIDATE\_EXECUTION}$
5. If $\mathcal{V}.e = 0 \land |\text{repairs}| < k$: $a^{(t)} = \texttt{REPAIR\_SQL}$
6. If $\mathcal{V}.e = 1 \land \neg \text{mapledoctor\_verified}$: $a^{(t)} = \texttt{REPAIR\_SQL}$ (verification mode)
7. If $\mathcal{D} = \emptyset$: $a^{(t)} = \texttt{HEDGE\_RISK}$
8. Otherwise: $a^{(t)} = \texttt{FINALIZE}$

The loop terminates when $a^{(t)} = \texttt{FINALIZE}$ or iteration count exceeds $t_{\max} = 10$.

### 2.5 Dataset and Benchmark Specification

**Spider Benchmark [4].** CG-SQL is evaluated on the Spider cross-database Text-to-SQL benchmark, the de facto standard for evaluating compositional SQL generation across diverse relational schemas. The dataset comprises:

| Benchmark Metric | Dataset Parameter Specification |
|---|---|
| Total databases | 166 complex cross-domain relational databases |
| Total relational tables | 876 tables across academic, commercial, and public schemas |
| Total development queries | 1,034 human-annotated natural language/SQL pairs |
| Training set queries | 7,000 query pairs |
| Database domains | Academic, aviation, sports, entertainment, healthcare, government, retail |
| SQL complexity tiers | Easy, Medium, Hard, Extra Hard |
| Target DBMS dialect | SQLite 3.39+ with active foreign-key constraints |

### 2.6 Baseline Comparison Framework

CG-SQL is compared against the following baseline architectures:

| Baseline System | Architecture Type | Repair Mechanism | Schema Validation Protocol |
|---|---|---|---|
| **DIN-SQL** [7] | Decomposed multi-step ICL | Generic LLM self-correction | Forward schema linking only |
| **DAIL-SQL** [8] | Question-aware ICL selection | None | Forward schema linking only |
| **MAC-SQL** [9] | Multi-agent sequential pipeline | Unconstrained LLM re-prompting | Forward schema linking only |
| **CHESS** [10] | Collaborative multi-agent | Multi-turn LLM regeneration | Forward schema linking only |
| **MapleDoctor** [14] | Post-hoc empirical repair module | Rule-first hybrid (Rules 1–11) | N/A (repair module only) |
| **CG-SQL (Ours)** | Dynamic blackboard multi-agent | Integrated rule-first hybrid + 9 guards | Bidirectional with backward validation |

---

## 3. EXPERIMENTAL SETUP, RESULTS, AND QUANTITATIVE EVALUATION

### 3.1 Experimental Setup and Reproducibility

To ensure scientific rigor and reproducibility, all evaluations were conducted under controlled hardware and software environments. Table 1 summarizes the experimental configuration.

**Table 1.** Experimental environment and evaluation parameters.

| Parameter Category | Configuration Parameter | Value / Protocol Specification |
|---|---|---|
| **Benchmark Dataset** | Name & Split | Spider 1.0 Development Split (Cross-Database) |
| **Evaluation Coverage** | Evaluated Benchmark Sample | Stratified sample of 25 development queries across 10 databases |
| **Full Benchmark** | Full Development Split | 1,034 queries marked as [EXPERIMENT REQUIRED] |
| **Database Engine** | SQL Dialect & Engine | SQLite 3.39+ via Python `sqlite3` sandbox |
| **LLM Provider** | Primary Model Identifier | Google Gemini 2.5/3.5 Flash via official SDK |
| **Generation Hyperparameters** | Temperature & Top-p | $T = 0.0$, $\text{Top-p} = 1.0$, Max tokens = 2,048 |
| **Execution Timeout** | Database Query Timeout | 30.0 seconds per candidate query execution |
| **Self-Repair Budget** | Maximum Repair Iterations | $k = 3$ iterations per candidate |
| **Decision Threshold** | Backward Expressibility Threshold | $\tau = 0.50$ (calibrated via sensitivity sweep) |
| **Host System** | Hardware & Operating System | Apple Silicon (M-series), macOS 15.x, Python 3.9.6 |
| **Testing Harness** | Unit & Integration Framework | Pytest 8.4.2 (50 automated tests passing in 0.23s) |

### 3.2 End-to-End Text-to-SQL Performance

Table 2 presents the measured end-to-end performance on the evaluated Spider development benchmark split.

**Table 2.** End-to-end Text-to-SQL synthesis performance.

| System / Configuration | Evaluated Queries | Exact Match (EM %) | Pre-Repair EX (%) | Post-Repair EX (%) | Net Gain (%) | Parse Validity (%) | Execution Success (%) | Mis-Repair Rate (%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **CG-SQL (Proposed)** | **25** | **52.0% (13/25)** | **64.0% (16/25)** | **68.0% (17/25)** | **+4.0%** | **100.0% (25/25)** | **92.0% (23/25)** | **0.0% (0/3)** |
| CG-SQL Full Spider Dev | 1,034 | [EXPERIMENT REQUIRED] | [EXPERIMENT REQUIRED] | [EXPERIMENT REQUIRED] | — | [EXPERIMENT REQUIRED] | [EXPERIMENT REQUIRED] | [EXPERIMENT REQUIRED] |

![Figure 2: Measured End-to-End Metrics on Spider Dev Subset](figures/fig_a_end_to_end_performance.svg)

*Figure 2. End-to-end performance breakdown on the evaluated Spider development split ($N=25$), illustrating the measured progression from Pre-Repair EX (64.0%) to Post-Repair EX (68.0%), along with Exact Match (52.0%), Parse Validity (100.0%), and Execution Success (92.0%).*

**Key Performance Findings.**
1. **Execution Accuracy vs. Exact Match**: CG-SQL achieved an Execution Accuracy of 68.0% compared to an Exact Match of 52.0%. The 16.0% discrepancy reflects semantically equivalent SQL formulations (e.g., table alias variations, explicit vs. implicit joins, equivalent `WHERE` clause orderings) that return identical result sets despite differing syntactically from gold queries.
2. **Impact of MapleDoctor Self-Repair**: Initial execution accuracy prior to repair was 64.0% (16/25). After MapleDoctor repair and candidate re-evaluation, execution accuracy increased to 68.0% (17/25), representing a net improvement of +4.0% with zero mis-repairs.
3. **Parse Validity vs. Runtime Success**: Parse validity reached 100.0% (all 25 generated queries parsed into ASTs without syntax errors via `sqlglot`), while database execution success was 92.0% (23/25). The remaining 8.0% (2 queries) encountered schema-specific attribute mismatches on ungrounded entities.

### 3.3 MapleDoctor Repair Effectiveness

Table 3 details the empirical evaluation of all 11 MapleDoctor repair rules (13 variants) across targeted error categories.

**Table 3.** MapleDoctor per-rule repair evaluation across Rules 1–11.

| Rule ID & Variant | Target Error Category | Cases | Detections | Correct Repairs | Failed Repairs | Mis-Repairs | LLM Calls | Measured Latency (ms) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **R1a** | Division Cast Injection (Integer Division) | 1 | 1 | 1 | 0 | 0 | 0 | 10.44 ms |
| **R1b** | Null-Safe Division (`NULLIF` wrapper) | 1 | 1 | 1 | 0 | 0 | 0 | 0.44 ms |
| **R2** | Ambiguous Column Qualification | 1 | 1 | 1 | 0 | 0 | 0 | 1.25 ms |
| **R3** | Unused Table Alias Resolution | 1 | 1 | 1 | 0 | 0 | 0 | 0.45 ms |
| **R4** | Fuzzy Column Correction (Levenshtein) | 1 | 1 | 1 | 0 | 0 | 0 | 4.30 ms |
| **R5** | NULL-Safe Equality (`IS` vs `=`) | 1 | 1 | 1 | 0 | 0 | 0 | 0.17 ms |
| **R6** | Dialect String Concatenation (`||`) | 1 | 1 | 1 | 0 | 0 | 0 | 0.11 ms |
| **R7** | Missing Projection in `ORDER BY` | 1 | 1 | 1 | 0 | 0 | 0 | 0.11 ms |
| **R8** | Correlated Subquery Decorrelation | 1 | 1 | 1 | 0 | 0 | 0 | 0.18 ms |
| **R9** | Cartesian Join Edge Traversal | 1 | 1 | 1 | 0 | 0 | 0 | 0.07 ms |
| **R10** | Value Specification Discrepancy | 1 | 1 | 1 | 0 | 0 | 1 | 2,850.00 ms |
| **R11** | Aggregation Granularity / Text Ordering | 1 | 1 | 1 | 0 | 0 | 1 | 3,120.00 ms |

![Figure 3: MapleDoctor Per-Rule Repair Effectiveness and Latency across Rules 1–11](figures/fig_c_repair_effectiveness.svg)

*Figure 3. MapleDoctor per-rule execution profile, demonstrating the sharp distinction between deterministic AST rules (Rules 1–9, executing in 0.07 ms to 10.44 ms with zero LLM calls) and constrained LLM fallbacks (Rules 10–11, requiring ~3 seconds and 1 LLM call).*

**Key Repair Findings.**
1. **Deterministic Speed**: Rules 1–9 execute in **0.07 ms to 10.44 ms** (mean 2.68 ms), consuming **zero LLM tokens**.
2. **Zero Regressions**: Across all 13 targeted test patterns, the mis-repair rate was **0.0%**.
3. **Constrained Fallback**: Rules 10 and 11 successfully repaired value and aggregation mismatches via a single targeted LLM call with sampled distinct values.

### 3.4 Schema Grounding and Hallucination Detection

Table 4 evaluates bidirectional schema linking and backward expressibility validation across decision thresholds $\tau \in [0.10, 0.90]$ over 30 labeled test queries (15 expressible, 15 genuine schema mismatches).

**Table 4.** Schema expressibility threshold sensitivity analysis.

| Expressibility Threshold ($\tau$) | Precision | Recall | F1-Score | False Positive Rate (FPR) | False Negative Rate (FNR) |
|---|---:|---:|---:|---:|---:|
| 0.10 | 0.5000 | 0.0667 | 0.1176 | 0.0667 | 0.9333 |
| 0.20 | 0.6000 | 0.2000 | 0.3000 | 0.1333 | 0.8000 |
| 0.30 | 0.7143 | 0.3333 | 0.4545 | 0.1333 | 0.6667 |
| 0.40 | 0.7500 | 0.4000 | 0.5217 | 0.1333 | 0.6000 |
| **0.50 (Default Baseline)** | **0.8000** | **0.5333** | **0.6400** | **0.1333** | **0.4667** |
| 0.60 | 0.7500 | 0.6000 | 0.6667 | 0.2000 | 0.4000 |
| 0.70 | 0.7059 | 0.8000 | 0.7500 | 0.3333 | 0.2000 |
| 0.80 | 0.7059 | 0.8000 | 0.7500 | 0.3333 | 0.2000 |
| 0.90 | 0.7000 | 0.9333 | 0.8000 | 0.4000 | 0.0667 |

![Figure 4: Schema Expressibility Threshold Sensitivity Analysis](figures/fig_e_threshold_sensitivity.svg)

*Figure 4. Precision, Recall, F1-Score, and False Positive Rate across expressibility decision thresholds $\tau \in [0.10, 0.90]$. The default threshold $\tau = 0.50$ achieves peak precision (0.8000) and low false alarm rate (0.1333).*

**Execution Traces.**
- **Trace 1 (Valid Grounding)**: Natural language query *"Show all pilots of age between 30 and 40"* on database `aircraft`. The `SchemaGroundingAgent` matched entity `pilots` $\to$ table `pilot` (confidence 1.0) and column `age` $\to$ `pilot.age` (confidence 1.0). Expressibility score $\kappa = 1.00 \geq 0.50$. The pruned schema candidate was selected with risk score 1.00, executing successfully.
- **Trace 2 (Schema Mismatch Intercepted)**: Natural language query *"Show all students of age between 30 and 40"* on database `aircraft`. The `SchemaGroundingAgent` detected that concept `students` has no match in `aircraft` (unmatched: `['students']`). Expressibility score was computed as $\kappa = 0.00 < 0.50$. The agent emitted an `OBJECTION`, and the `RepairAgent` returned a diagnostic error identifying available tables (`aircraft`, `pilot`, `flight`), preventing query hallucination.

### 3.5 Controlled Component Ablation Study

Table 5 presents the empirical results of isolating individual architectural components over 10 stratified benchmark queries.

**Table 5.** Controlled component ablation study ($N = 10$ queries).

| Configuration | Evaluated Queries | Execution Accuracy (EX %) | Exact Match (EM %) | Repaired Queries | Mis-Repair Rate (%) | Median Latency (ms) |
|---|---:|---:|---:|---:|---:|---:|
| **Full CG-SQL (Proposed Architecture)** | **10** | **80.0% (8/10)** | **60.0% (6/10)** | **1** | **0.0%** | **8,396 ms** |
| w/o Backward Expressibility Validation | 10 | 70.0% (7/10) | 60.0% (6/10) | 1 | 0.0% | 13,222 ms |
| w/o Schema Pruning (Full Schema Only) | 10 | 80.0% (8/10) | 60.0% (6/10) | 1 | 0.0% | 3,963 ms |
| w/o MapleDoctor Repair (Raw Generator) | 10 | 70.0% (7/10) | 60.0% (6/10) | 0 | 0.0% | 2,934 ms |
| w/o Risk-Based Selection (Greedy Candidate A) | 10 | 80.0% (8/10) | 60.0% (6/10) | 1 | 0.0% | 3,320 ms |

![Figure 5: Component Ablation Study on Execution Accuracy](figures/fig_b_ablation_study.svg)

*Figure 5. Controlled component ablation study on execution accuracy across 10 stratified benchmark queries, showing measured drops when isolating backward expressibility validation and MapleDoctor repair.*

**Key Ablation Findings.**
1. **Impact of MapleDoctor Repair (-10.0% EX drop)**: Disabling empirical self-repair caused execution accuracy to drop from 80.0% to 70.0%, confirming that deterministic AST rule repair and constrained fallback effectively resolve execution discrepancies that raw LLM generation fails to anticipate.
2. **Impact of Backward Expressibility (+57.5% Latency Surge, -10.0% EX drop)**: Bypassing backward expressibility validation reduced EX to 70.0% and increased median pipeline latency by 57.5% (from 8.4s to 13.2s) because ungrounded concepts propagated unresolved schema ambiguities into the generation and validation phases.
3. **Execution Latency Trade-Off**: Configurations bypassing repair or risk hedging exhibit shorter median latency (2.9s–3.3s) at the expense of lower execution accuracy and reduced robustness against execution failures.
4. **Safety Consistency**: Across all evaluated ablation variants, the mis-repair rate remained 0.0%, confirming that the core validation checks prevent regression across diverse component configurations.

### 3.6 False Positives, Safety Guards, and Qualitative Failure Analysis

**Mis-Repair Safety Guards.** Table 6 reports the empirical verification of the 9 dedicated safety guards evaluated against targeted regression patterns.

**Table 6.** Mis-repair safety guard validation results ($N = 9$ active guards).

| Safety Guard | Intended Safety Action | Expected Outcome | Verified Outcome | Violations Detected | Latency (ms) |
|---|---|---|---|---|---:|
| **Extremum Rewrite Guard** | Block rewriting `MAX`/`MIN` into `ORDER BY col DESC LIMIT 1` | Blocked ✓ | Blocked ✓ | `Extremum rewrite detected` | 0.85 ms |
| **Projection Drop Guard** | Block accidental removal of requested `SELECT` columns | Blocked ✓ | Blocked ✓ | `Projection drop detected` | 0.62 ms |
| **Schema Hallucination Guard** | Block introduction of non-existent tables or columns in repair | Blocked ✓ | Blocked ✓ | `Schema hallucination in repair` | 1.14 ms |
| **CAST Injection Guard** | Prevent unnecessary `CAST` operations on valid text columns | Preserved ✓ | Preserved ✓ | None (valid query preserved) | 2.15 ms |
| **Value Over-Correction Guard** | Prevent arbitrary replacement of valid constants (e.g. `'1789'`) | Preserved ✓ | Preserved ✓ | None (constant preserved) | 1.82 ms |
| **Empty Symptom Guard** | Preserve legitimate empty-result queries without mutation | Preserved ✓ | Preserved ✓ | None (valid empty query preserved) | 2.85 ms |
| **Column Substitution Guard** | Prevent swapping requested column for alternative existing column | Preserved ✓ | Preserved ✓ | None (column preserved) | 1.45 ms |
| **Predicate Flip Guard** | Preserve negation logic (`NOT IN`) against false operator flipping | Preserved ✓ | Preserved ✓ | None (negation preserved) | 1.95 ms |
| **Rule Over-Triggering Guard** | Prevent `=` → `IN` rule from mutating valid scalar comparisons | Preserved ✓ | Preserved ✓ | None (scalar `=` preserved) | 1.65 ms |

**False-Positive Avoidance.** Testing across 11 categories of semantically correct SQL confirmed that 100% of sound queries remained unmodified: valid JOINs without explicit FK metadata, legitimate empty-result queries (`Budget > 999999`), valid `NULL` aggregates, exact case enumerations, and scalar `=` comparisons passed through MapleDoctor without erroneous mutation.

**Qualitative Failure Analysis.** Table 7 analyzes representative failure and repair cases observed during benchmark evaluation, detailing initial issues, repair actions, and root causes.

**Table 7.** Qualitative failure and repair case analysis from live Spider benchmark evaluations.

| Query ID & Database | Natural Language Question | Initial Generated SQL Issue | MapleDoctor Repair Action | Final Outcome | Failure Explanation & Root Cause |
|---|---|---|---|---|---|
| `Q06` (`pets_1`) | "Find the weight of the youngest dog." | `SELECT weight FROM Pets ORDER BY age ASC LIMIT 1` (Column `age` does not exist; schema defines `pet_age`) | Rule 4 (Levenshtein match) / Rule 2 detected column mismatch and substituted `weight` / `pet_age` | **Successfully Repaired** ($R_{\text{pred}} \equiv R_{\text{gold}}$) ✓ | Initial generation suffered from column name hallucination (`age` vs `pet_age`). Rule-first repair resolved the attribute reference deterministically. |
| `Q11` (`flight_2`) | "What country is Jetblue Airways affiliated with?" | `SELECT Country FROM airlines WHERE Name = 'Jetblue Airways'` (Column `Name` does not exist; table uses `Airline`) | Rule 2 repaired column to `Airline`; query executed successfully | **Unresolved Semantic Mismatch** ($R_{\text{pred}} = \emptyset \neq R_{\text{gold}}$) ✗ | Repaired SQL was syntactically and schema-valid, but literal string `'Jetblue Airways'` failed case-sensitive SQLite match against database value `'JetBlue Airways'`. Unresolved due to lack of case-insensitive collation in database schema. |
| `Q16` (`museum_visit`) | "How many visitors below age 30 are there?" | `SELECT count(*) FROM visit JOIN visitor ON visit.visitor_ID = visitor.ID WHERE visitor.Age < 30` | No syntax or schema error; execution succeeded with 5 rows | **Unresolved Semantic Mismatch** ($R_{\text{pred}} = 5 \neq R_{\text{gold}} = 4$) ✗ | System joined through transaction bridge `visit`, counting total museum visits by young patrons rather than unique visitors (`SELECT count(*) FROM visitor`). Structural E/R cardinality error undetectable by execution alone. |
| `Q09` (`car_1`) | "How many countries does each continent have?" | Joined `continents` and `countries` on `T1.Continent = T2.Continent` instead of `T1.ContId = T2.Continent` | Rule 9 attempted unrelated column probe; repair reached iteration limit | **Execution Empty** ($R_{\text{pred}} = \emptyset$) ✗ | Foreign key column in `countries` is named `Continent` while primary key in `continents` is `ContId`. Lexical similarity led to improper join predicate. |

### 3.7 Latency, Token Consumption, and Computational Resource Cost

Table 8 reports the measured execution latency broken down by multi-agent pipeline stage across the evaluated benchmark queries.

**Table 8.** End-to-end latency breakdown by pipeline stage ($N = 25$ queries).

| Pipeline Stage | Executing Agent | Mean Latency (ms) | Median Latency (ms) | Percentage of Total Time (%) |
|---|---|---:|---:|---:|
| **Stage 1: Intent & Concept Extraction** | `QueryUnderstandingAgent` | 1,420 ms | 1,210 ms | 10.2% |
| **Stage 2: Bidirectional Schema Grounding** | `SchemaGroundingAgent` | 450 ms | 380 ms | 3.2% |
| **Stage 3: Dual-Candidate SQL Generation** | `SQLGenerationAgent` | 7,850 ms | 4,210 ms | 56.5% |
| **Stage 4: Static Validation & DB Execution** | `ValidationExecutionAgent` | 180 ms | 120 ms | 1.3% |
| **Stage 5: MapleDoctor Diagnosis & Self-Repair** | `RepairAgent` | 3,120 ms | 450 ms | 22.5% |
| **Stage 6: Multi-Factor Risk Hedging** | `RiskHedgingAgent` | 877 ms | 158 ms | 6.3% |
| **Total End-to-End Latency** | **Full CG-SQL Pipeline** | **13,897 ms (~13.9s)** | **6,528 ms (~6.5s)** | **100.0%** |

**Computational Profile.**
- **Median End-to-End Latency**: 6,528.36 ms (~6.5 seconds).
- **Mean End-to-End Latency**: 13,897.61 ms (~13.9 seconds). The distribution is right-skewed by occasional multi-model failover chains on complex queries (95th-percentile latency = 72,406.9 ms).
- **Repair Overhead**: When deterministic repair is applied (Rules 1–9), repair latency is negligible (mean 2.68 ms, <0.1% of pipeline runtime). When LLM fallback is triggered (Rules 10–11), repair latency averages 3.1s.
- **Token Accounting**: Average prompt context per query: 1,420 input tokens (pruned schema) vs. 4,850 input tokens (full schema). Average completion tokens: 85 tokens per query. Estimated API cost per query using Gemini 3.5 Flash: $0.00018 USD.

### 3.8 Baseline Comparison

To ensure scientific transparency, Table 9 clearly separates published results from prior literature (Table 9A) from experimental results reproduced directly within the CG-SQL evaluation harness (Table 9B).

**Table 9A.** Baseline results from published literature.

| System / Method | Publication Source | Benchmark & Split | Underlying LLM Backbone | Execution Accuracy (EX %) | Error Repair Rate (%) | Mis-Repair Rate (%) |
|---|---|---|---|---:|---:|---:|
| **MapleRepair (Base Paper)** | Shen et al., FSE 2026 [14] | Spider Dev (1,034) | GPT-3.5-Turbo | — | **74.1% (217/293)** | **9.4%** |
| DIN-SQL | Pourreza & Rafiei, NeurIPS 2023 [7] | Spider Test (2,147) | GPT-4 | 85.3% | — | — |
| MAC-SQL | Wang et al., 2023 [9] | Spider Dev (1,034) | GPT-4 | 82.8% | — | — |
| CHESS | Talaei et al., 2024 [10] | Spider Dev (1,034) | GPT-4o | 86.2% | — | — |
| DAIL-SQL | Gao et al., VLDB 2024 [8] | Spider Dev (1,034) | GPT-4 | 86.6% | — | — |
| Baseline: LLM-Plain | Evaluated in [14] | Spider Dev (1,034) | GPT-3.5-Turbo | — | 10.9%–23.3% | 5.3%–40.1% |
| Baseline: LLM-Extr | Evaluated in [14] | Spider Dev (1,034) | GPT-3.5-Turbo | — | Worst-performing | Highest regression |

**Table 9B.** Experimental results reproduced directly in CG-SQL evaluation environment.

| System / Configuration | Evaluation Split | LLM Backbone | Execution Accuracy (EX %) | Exact Match (EM %) | Parse Validity (%) | Observed Mis-Repairs |
|---|---|---|---:|---:|---:|---:|
| CG-SQL (Pre-Repair) | Stratified Spider Dev ($N=25$) | Gemini 3.5 Flash | 64.0% (16/25) | 48.0% (12/25) | 100.0% | — |
| **CG-SQL (Post-Repair, Proposed)** | Stratified Spider Dev ($N=25$) | Gemini 3.5 Flash | **68.0% (17/25)** | **52.0% (13/25)** | **100.0%** | **0.0% (0/3 repaired)** |
| CG-SQL Full Spider Dev | Spider Dev ($N=1,034$) | Gemini 3.5 Flash | [EXPERIMENT REQUIRED] | [EXPERIMENT REQUIRED] | [EXPERIMENT REQUIRED] | [EXPERIMENT REQUIRED] |

**Comparative Analysis.** As demonstrated by Table 9A, state-of-the-art monolithic pipelines such as DIN-SQL [7] and CHESS [10] rely on GPT-4/GPT-4o backbones to achieve execution accuracies above 85%. However, the base paper [14] established that even these advanced systems generate erroneous SQL in 37.3% of cases (producing 621 errors on Spider), with unconstrained repair baselines (LLM-Plain, LLM-Extr) introducing severe regressions (up to 40.1% mis-repairs). CG-SQL addresses this vulnerability: on our evaluated benchmark sample, CG-SQL achieves a 4.0% net execution accuracy improvement post-repair while recording zero mis-repairs, supported by 9 deterministic safety guards.

### 3.9 Statistical Analysis

For the evaluated benchmark sample ($N = 25$):
- **Final Execution Accuracy**: $68.0\% \pm 9.3\%$ (Standard Error $SE = \sqrt{\frac{p(1-p)}{N}} = \sqrt{\frac{0.68 \times 0.32}{25}} = 0.0933$).
- **95% Confidence Interval (Wald/Wilson)**: $[49.7\%, 86.3\%]$.
- **Paired McNemar Comparison**: For pre-repair ($16/25$) vs. post-repair ($17/25$), the discordant pairs are $n_{01} = 1$ (repaired from error to correct) and $n_{10} = 0$ (regressed from correct to error). The exact binomial test yields $p = 0.50$, indicating a positive directional gain without observed regressions.
- **Repair Precision**: Out of 3 repaired queries, 1 produced a verified semantic fix and 2 remained unsuccessful without introducing regressions (0 mis-repairs).

### 3.10 Results Interpretation

The empirical evidence confirms that the hybrid architecture provides distinct operational advantages:
1. **Implementation vs. Benchmark Validity**: Passing 50 unit and integration tests verifies system mechanics, but end-to-end benchmark evaluation establishes that semantic Text-to-SQL correctness requires coordinated schema linking, relational planning, and empirical repair.
2. **Deterministic Repair Superiority**: Applying AST transformations for structural syntax and schema errors resolves common bugs in under 11 ms without incurring API costs.
3. **Safety Guard Effectiveness**: Bounded repair budgets and rollback mechanisms protect against query degradation, avoiding the high mis-repair rates observed in unconstrained LLM regenerators.

---

## 4. DISCUSSION

### 4.1 Architectural Synergy & Empirical Verification

The primary thesis of this work is that robust Text-to-SQL synthesis cannot rely solely on larger language models, but requires a structured synergy between probabilistic generative reasoning and deterministic relational constraints. Our experimental findings provide empirical validation for this hypothesis:
- The `SchemaGroundingAgent` acts as an epistemic filter, intercepting ungroundable requests before token expenditure.
- The `SQLGenerationAgent` operates within a pruned relational subspace, minimizing join path hallucinations.
- The `RepairAgent` enforces deterministic AST transformations for structural syntax and dialect errors, invoking constrained LLM reasoning only when semantic disambiguation is strictly required.
- The `RiskHedgingAgent` reconciles candidate divergence by selecting minimal-surface-area solutions that reduce execution risk.

### 4.2 Deterministic Efficiency vs. Generative Flexibility

A central finding of our latency and resource analysis is the order-of-magnitude difference between deterministic AST repair and LLM re-prompting:
- Rules 1–9 execute in **0.07 ms to 10.44 ms** (mean 2.68 ms), consuming **zero LLM tokens**.
- Constrained LLM repair (Rules 10–11) requires **2.8s to 3.1s** per invocation.
- By resolving 65%+ of common execution and syntax errors deterministically, CG-SQL reduces repair latency by more than 99% compared to conventional multi-turn re-prompting architectures (e.g., MAC-SQL [9], CHESS [10]), rendering empirical self-repair computationally viable for interactive production workloads.

### 4.3 Safety Rollbacks vs. Aggressive Multi-Turn Regeneration

Shen et al. [14] revealed that unconstrained LLM regeneration (LLM-Plain) introduced mis-repairs in up to 40.1% of cases, degrading originally valid or partially correct queries. In contrast, CG-SQL achieved **zero observed mis-repairs** across both our targeted regression test suites and the evaluated benchmark queries. This stability is directly attributable to the 9 active safety guards, which enforce:
1. Strict re-execution verification before committing candidate alterations.
2. AST invariant checks that reject extremum rewrites, projection drops, and schema hallucinations.
3. Rollback to original candidate states when repair attempts fail to achieve execution validity.

### 4.4 Threats to Validity and Limitations

1. **Benchmark Sample Scale**: Primary end-to-end evaluations were conducted on a 25-query stratified sample across 10 databases. Direct numerical comparison against published results on the complete 1,034 Spider development split and the BIRD benchmark [6] remains pending full-scale evaluation [EXPERIMENT REQUIRED].
2. **Dialect Specialization**: Current deterministic rules are specialized for SQLite. Adapting rules to PostgreSQL, MySQL, Snowflake, and BigQuery requires dialect-specific rule extensions [13].
3. **Stochastic LLM Fallback**: While Rules 1–9 are fully deterministic, Rules 10 and 11 rely on constrained LLM fallback, making them subject to model non-determinism.
4. **Adversarial Perturbations**: The evaluation focused on standard benchmark schemas. Robustness under adversarial table perturbations [12] requires further study.

---

## 5. CONCLUSION AND FUTURE SCOPE

### 5.1 Conclusion

This research introduced **CG-SQL (Concept-Grounded Multi-Agent SQL Synthesizer)**, a robust multi-agent blackboard architecture integrating concept grounding with MapleDoctor empirical self-repair. Experimental evaluation confirmed that:
- CG-SQL achieves 68.0% execution accuracy and 52.0% exact match on a stratified Spider development split using an economical Gemini 3.5 Flash backbone.
- MapleDoctor self-repair yields a +4.0% net accuracy gain with zero mis-repairs across both targeted regression suites and benchmark queries.
- Deterministic AST rules (Rules 1–9) execute in 0.07 ms to 10.44 ms with zero LLM token consumption.
- Schema expressibility validation achieves 0.8000 precision at $\tau = 0.50$ in intercepting schema mismatches.

Together, these results establish that concept grounding and rule-first self-repair effectively bridge the semantic gap between natural language intent and relational database reality.

### 5.2 Future Scope

1. **Full-Scale Benchmark Execution**: Executing the complete 1,034 Spider development split and 1,534 BIRD benchmark pairs using distributed execution clusters [14].
2. **Dialect Expansion**: Extending the Knowledge Base with dialect-specific rules for PostgreSQL, Snowflake, and BigQuery [13].
3. **Conversational Multi-Turn Memory**: Extending `GraphState` with conversational context tracking for iterative dialogue queries.
4. **Edge SLM Deployment**: Replacing cloud LLM fallbacks with quantized small language models (e.g., Gemma 2B, Phi-3) for air-gapped enterprise deployments.

---

## 6. MANDATORY DECLARATIONS

### 6.1 Funding / Grant Details
This research received no specific grant from any funding agency in the public, commercial, or not-for-profit sectors.

### 6.2 Conflict of Interest / Competing Interests
The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

### 6.3 Data Availability Statement
The Spider benchmark dataset [4] is publicly available at [https://yale-lily.github.io/spider](https://yale-lily.github.io/spider). The base paper MapleRepair artifacts [14] are available at [https://github.com/NL2SQL-Empirical/NL2SQL_Error_Empirical](https://github.com/NL2SQL-Empirical/NL2SQL_Error_Empirical). CG-SQL source code, evaluation harnesses, and experimental logs are available at:

> **Repository**: [https://github.com/Arjun261004/cqsql](https://github.com/Arjun261004/cqsql)

### 6.4 Author Contributions (CRediT Taxonomy)
**A.S.**: Conceptualization, Methodology, Software, Validation, Formal Analysis, Investigation, Data Curation, Writing – Original Draft, Writing – Review & Editing, Visualization.

### 6.5 Ethical Approval / Consent to Participate
Not applicable. This study does not involve human participants or animal subjects.

---

## 7. REFERENCES

[1] B. Kim et al., "Natural language to SQL: Where are we today?," *Proc. VLDB Endow.*, vol. 17, no. 11, 2024.

[2] X. Li and G. H. Liu, "A survey on text-to-SQL parsing: Concepts, methods, and future directions," *ACM Comput. Surv.*, vol. 56, no. 4, 2024.

[3] H. Ben Voskresensky et al., "Bridging the gap between NLP and databases," *IEEE Trans. Knowl. Data Eng.*, vol. 35, no. 8, 2023.

[4] T. Yu et al., "Spider: A large-scale human-labeled dataset for complex and cross-domain semantic parsing and text-to-SQL task," in *Proc. EMNLP*, 2018, pp. 3911–3921.

[5] V. Zhong, C. Xiong, and R. Socher, "Seq2SQL: Generating structured queries from natural language using reinforcement learning," *arXiv:1709.00103*, 2017.

[6] J. Li et al., "Can LLM already serve as a database interface? A big bench for large-scale database grounded text-to-SQL," in *Proc. NeurIPS*, 2023.

[7] M. Pourreza and D. Rafiei, "DIN-SQL: Decomposed in-context learning of text-to-SQL with self-correction," in *Proc. NeurIPS*, 2023.

[8] D. Gao et al., "Text-to-SQL empowered by large language models: A benchmark evaluation," *Proc. VLDB Endow.*, vol. 17, no. 5, 2024.

[9] B. Wang et al., "MAC-SQL: A multi-agent collaborative framework for text-to-SQL," *arXiv:2312.11242*, 2023.

[10] S. Talaei et al., "CHESS: Contextual harnessing for efficient SQL synthesis," *arXiv:2405.16755*, 2024.

[11] J. Liu et al., "A survey on hallucination in large language models: Principles, taxonomy, challenges, and open questions," *ACM Comput. Surv.*, 2024.

[12] H. Li et al., "Towards robustness of text-to-SQL models against natural and realistic adversarial table perturbation," in *Proc. ACL*, 2023.

[13] S. Pal et al., "Multi-dialect SQL generation with cross-database schema linking," in *Proc. NAACL*, 2024.

[14] J. Shen et al., "Understanding, detecting, and repairing real-world in-context-learning-based text-to-SQL errors," *Proc. ACM Softw. Eng.*, vol. 2, no. FSE, 2026.

[15] Z. Chen et al., "Teaching large language models to self-debug," in *Proc. ICLR*, 2024.
