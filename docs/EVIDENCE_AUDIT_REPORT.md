# Comprehensive Evidence Audit Report: CG-SQL Experimental Validation

**Project:** CG-SQL (Concept-Grounded Multi-Agent SQL Synthesizer with MapleDoctor-Integrated Empirical Self-Repair)  
**Target Submission:** Scopus-Indexed Computer Science / Software Engineering Journal  
**Audit Date:** October 20, 2026  
**Auditor:** Senior Research Scientist & Experimental Methodology Specialist  

---

## 1. Executive Summary

This audit evaluates the empirical foundation of the CG-SQL research paper against the actual repository implementation, automated test suites, dataset assets, and experimental evaluation runs. The audit distinguishes between:
1. **Fully Verified Claims**: Backed by measured, reproducible execution data on target databases.
2. **Targeted / Unit-Level Evidence**: Validated in isolated unit/integration tests on specific synthetic test cases, which cannot be conflated with general benchmark performance.
3. **Published Literature Evidence**: Accurately attributed findings from the base paper (Shen et al., *Proc. ACM Softw. Eng.*, FSE 2026) and contemporary text-to-SQL baselines.
4. **Unsupported / Conflated Claims in Previous Draft**: Statements that previously overstated scope (e.g., treating a 50-test suite as benchmark coverage, or test runtime as query latency).
5. **Completed vs. Pending Experiments**: Status of empirical evaluations conducted during this overhaul.

---

## 2. Granular Evidence Classification Matrix

| Claim / Metric in Paper | Actual Evidence Source | Evidence Classification | Verification Status | Action Taken in Manuscript |
|---|---|---|---|---|
| **50-Test Suite Pass Rate** | `tests/` executed via `pytest 8.4.2` | Unit / Integration Testing | **Verified (50/50 passed in 0.50s)** | Strictly reported as component functional verification; decoupled from benchmark execution accuracy. |
| **0.27s Test Suite Execution** | `pytest` wall-clock time | Test Suite Runtime | **Verified as test runtime, INVALID as query latency** | Removed from latency claims; real end-to-end query latency measured separately (median 6.5s). |
| **Spider Benchmark Evaluation** | `experiments/run_benchmark_eval.py` | Live SQLite Execution on Stratified Dev Sample | **Verified (N=25: EX=68.0%, EM=52.0%)** | Replaces unverified 1,034-query claim with exact stratified sample metrics and limitations. |
| **Pre- vs. Post-Repair Accuracy** | `experiments/results/benchmark_query_results.json` | Paired query execution comparison | **Verified (Initial EX: 64.0% -> Final EX: 68.0%, +4.0% gain)** | Documented in Section 4.2 with exact per-query breakdown and repair tracking. |
| **Zero Mis-Repairs (Safety)** | `tests/test_mapledoctor_misrepair_safety.py` + `run_mapledoctor_eval.py` | 9 Unit Safety Guards + Benchmark Sample | **Verified on Tested Cases (0 regressions on tested suite & sample)** | Qualified explicitly: zero regressions observed within the tested 9 guard patterns and evaluated benchmark sample. |
| **MapleDoctor Per-Rule Repair** | `experiments/run_mapledoctor_eval.py` | 13 Rule-Targeted Test Cases on `department_management` | **Verified on Targeted Cases (13/13 repaired)** | Clear separate denominators per rule; latencies reported as measured CPU time (0.07 ms to 10.44 ms). |
| **Schema Grounding Threshold Sensitivity** | `experiments/run_grounding_eval.py` | Labeled 30-query dataset swept over $\tau \in [0.10, 0.90]$ | **Verified (Peak Precision 0.8000 at $\tau=0.50$, Recall 0.9333 at $\tau=0.90$)** | Replaced hypothetical 0.50 assumption with full empirical ROC/trade-off curve in Section 4.4 and Figure 5. |
| **100% System Availability** | `src/agents/sql_generation_agent.py` (`_build_deterministic_sql`) | Architectural Fallback Engine | **Verified in Code / Unit Tests** | Clarified as an architectural failover property rather than a production operational SLA. |
| **Candidate Scoring Formula** | `src/agents/risk_hedging_agent.py` | Code Implementation | **Verified (+0.50, +0.30, +0.10, +0.10, -0.15, -0.20)** | Clarified as an empirical heuristic evidence score, not an uncalibrated Bayesian probability. |
| **Base Paper Comparison (MapleRepair)** | Shen et al., FSE 2026 [14] | Published Literature | **Verified against literature** | Placed in Table A (Published Literature); clearly segregated from CG-SQL reproduced data in Table B. |
| **Contemporary Baselines (DIN-SQL, MAC-SQL, CHESS)** | Literature [7], [9], [10] | Published Literature | **Verified against literature** | Clearly attributed as external literature references; no claim of local reproduction. |

---

## 3. Discrepancies Corrected from Previous Draft

1. **Conflation of Unit Tests with Benchmark Accuracy**:
   - *Previous draft:* Stated that all experiments were conducted on the Spider benchmark (1,034 queries) with 100% accuracy.
   - *Correction:* Accurately reports that the 50 automated tests evaluate rule-level isolation, safety guards, and integration pipelines. Benchmark execution accuracy is reported separately on a reproducible stratified sample of 25 development queries across 10 diverse databases (EX = 68.0%, EM = 52.0%). Full 1,034-query benchmark execution is explicitly identified as pending large-scale evaluation.
2. **Conflation of Test Runtime with Query Latency**:
   - *Previous draft:* Cited 0.27s test execution time as evidence of sub-second query latency.
   - *Correction:* Strictly separates test suite execution (0.50s for 50 unit tests) from end-to-end multi-agent query synthesis (median 6,528.36 ms, mean 13,897.61 ms), which includes LLM generation, schema grounding, static validation, and database probing.
3. **Unqualified Zero Mis-Repair Guarantee**:
   - *Previous draft:* Claimed a universal 0% mis-repair rate.
   - *Correction:* Qualified as zero mis-repairs observed across the 9 validated safety guard regression patterns and the evaluated benchmark sample.
4. **Denominators in Rule-Based Repair**:
   - *Previous draft:* Used an aggregate denominator implying a large-scale repair study.
   - *Correction:* Reported each rule with its explicit tested cases ($N=1$ per variant, total $N=13$), reporting exact measured execution time in milliseconds and LLM call counts (0 for Rules 1–9, 1 for Rules 10–11).
5. **Threshold Optimality Assumption**:
   - *Previous draft:* Assumed $\tau = 0.50$ is optimal without empirical data.
   - *Correction:* Evaluated $\tau \in [0.10, 0.90]$ across 30 labeled queries, demonstrating that $\tau = 0.50$ maximizes precision (0.8000) while keeping false positive rate low (0.1333), whereas higher thresholds increase recall at the cost of higher false alarms.

---

## 4. Status of Experimental Evaluations

### A. Completed Experiments (Data Collected & Verified)
1. **MapleDoctor Rule Verification**: 13 rule variants executed; detection and repair success verified; exact CPU latencies logged (`experiments/results/mapledoctor_rule_results.json`).
2. **Mis-Repair Safety Guard Verification**: 9 regression patterns tested; 100% correct blocking/preservation behavior verified (`experiments/results/mapledoctor_safety_results.json`).
3. **Schema Grounding Sensitivity Analysis**: 30 queries evaluated across 9 thresholds; Precision, Recall, F1, FPR, FNR, and Accuracy calculated (`experiments/results/grounding_threshold_sweep.json`).
4. **Stratified Spider Dev Benchmark**: 25 queries evaluated on live SQLite databases; Initial EX, Final EX, EM, Parse Validity, and Latencies measured (`experiments/results/benchmark_query_results.json`).

### B. Pending Experiments (Scripts Prepared, Marked Pending)
1. **Full Spider Dev Benchmark (N=1,034)**:
   - *Status*: Evaluation harness implemented (`experiments/run_benchmark_eval.py`). Full run across all 1,034 queries requires ~3–4 hours of continuous LLM API calls and may exceed external rate limits. Marked as pending in the manuscript.
2. **Large-Scale BIRD Benchmark (N=1,534)**:
   - *Status*: BIRD SQLite databases and execution harness prepared; large-scale run pending compute resources and marked as future scope.

---

## 5. Compliance with Journal Standards

This audit confirms that the revised experimental section adheres to Scopus/IEEE/ACM submission guidelines:
- Zero fabricated metrics or synthetic estimates.
- Clear demarcation between unit tests, sample benchmark results, and published literature.
- All numbers traceable to machine-readable JSON/CSV artifacts in `experiments/results/`.
- Explicit documentation of operational limits, failure modes, and threats to validity.
