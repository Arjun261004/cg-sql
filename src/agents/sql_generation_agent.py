import re
from typing import Dict, List, Any, Optional
from src.agents.base_agent import BaseAgent
from src.models.state import GraphState
from src.models.messages import AgentMessage, MessageType
from src.core.agent_registry import AgentDescriptor
from src.tools.dialect_resolver import DialectResolver
from src.tools.query_planner import QueryPlanner

class SQLGenerationAgent(BaseAgent):
    """
    AGENT 3 — SQLGenerationAgent
    Role: Convert grounded intent + grounded schema into executable SQL.
    Absorbs:
    - SQL Generator
    - Dialect Agent (determines dialect and fetches rules from KB)
    - Query Planner (relational planning, filtering, joins, CTE decomposition)
    - SQL Candidate Generation (Candidate A: full schema context vs Candidate B: pruned schema context)
    """
    def __init__(self, kb=None):
        super().__init__("SQLGenerationAgent", "Dialect-aware relational query planning and SQL candidate generation", kb=kb)
        self.dialect_resolver = DialectResolver(kb=kb)
        self.planner = QueryPlanner()

    def get_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            name=self.name,
            role=self.role,
            capabilities=[
                "dialect_resolution",
                "relational_query_planning",
                "cte_planning",
                "candidate_generation"
            ],
            tools=["dialect_resolver", "query_planner", "llm_sql_generator"],
            input_requirements=["concept_grounding", "schema_linking"],
            activation_conditions=["missing_sql_candidates"]
        )

    def observe(self, state: GraphState) -> None:
        self.dialect_resolver.kb = self.kb

    def reason(self, state: GraphState) -> None:
        pass

    def evaluate_evidence(self, state: GraphState) -> float:
        if state.sql_candidates:
            return state.sql_candidates[0].get("confidence", 0.90)
        return 0.85

    def _build_deterministic_sql(
        self,
        schema_context: Dict[str, Any],
        query_plan: Dict[str, Any],
        concept_grounding: Optional[Any] = None,
        schema_linking: Optional[Any] = None
    ) -> str:
        """Constructs an intelligent deterministic SQL query preserving intent and filters."""
        # Determine primary table
        tables = schema_context.get("tables", [])
        if schema_linking and schema_linking.unmatched_concepts:
            primary_table = schema_linking.unmatched_concepts[0]
        elif schema_linking and getattr(schema_linking, "final_tables", None):
            primary_table = schema_linking.final_tables[0]
        elif concept_grounding and concept_grounding.entities:
            ent = concept_grounding.entities[0]
            matched = next((t for t in tables if t.lower() == ent.lower() or t.lower() == ent.lower().rstrip('s')), None)
            primary_table = matched if matched else ent
        else:
            primary_table = tables[0] if tables else "dual"

        avail_cols = schema_context.get("columns", {}).get(primary_table, [])
        if not avail_cols and schema_linking and hasattr(schema_linking, "candidate_columns"):
            avail_cols = schema_linking.candidate_columns.get(primary_table, [])

        # Build WHERE filters
        where_clauses = []
        filters = []
        if concept_grounding and concept_grounding.filters:
            filters.extend(concept_grounding.filters)
        elif query_plan and query_plan.get("filters"):
            filters.extend(query_plan.get("filters"))

        for f in filters:
            raw_field = f.get("field", "")
            col = next((c for c in avail_cols if c.lower() == raw_field.lower()), raw_field)
            op = f.get("op", "=").upper()
            val = f.get("value")
            if op == "BETWEEN" and isinstance(val, (list, tuple)) and len(val) == 2:
                where_clauses.append(f"{col} BETWEEN {val[0]} AND {val[1]}")
            elif isinstance(val, (int, float)):
                where_clauses.append(f"{col} {op} {val}")
            elif isinstance(val, str):
                where_clauses.append(f"{col} {op} '{val}'")

        where_part = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Aggregations / Projection
        if concept_grounding and concept_grounding.aggregations and "COUNT" in concept_grounding.aggregations:
            select_part = "SELECT COUNT(*)"
        else:
            select_part = "SELECT *"

        limit_part = f" LIMIT {concept_grounding.limits}" if concept_grounding and concept_grounding.limits else ""
        return f"{select_part} FROM {primary_table}{where_part}{limit_part}".strip()

    def _generate_candidate_sql(
        self,
        schema_context: Dict[str, Any],
        intent: str,
        dialect: str,
        dialect_guidelines: str,
        query_plan: Dict[str, Any],
        candidate_type: str,
        db_path: str = "",
        concept_grounding: Optional[Any] = None,
        schema_linking: Optional[Any] = None
    ) -> str:
        """Generates SQL candidate constrained by provided schema context and dialect."""
        try:
            from src.core.llm_client import LLMClient
            llm = LLMClient()

            prompt = f"""
            You are an expert {dialect} SQL query generator.
            
            User Intent: "{intent}"
            
            Target Schema Context ({candidate_type}):
            Tables: {schema_context.get('tables', [])}
            Columns: {schema_context.get('columns', {})}
            
            Relational Execution Plan:
            {query_plan.get('steps', [])}
            
            {dialect_guidelines}
            
            CRITICAL GENERATION CONSTRAINTS:
            1. Generate the SQL query that faithfully addresses the User Intent.
            2. If the user intent's entities and attributes match the Target Schema Context, strictly reference those tables and columns.
            3. If the user intent requests entities or attributes (e.g. 'students', 'course') that do NOT exist in the Target Schema Context, do NOT substitute completely unrelated tables (such as substituting 'pilot' or 'aircraft' for 'students'). Instead, construct the query reflecting the user's requested entities and attributes so that downstream schema validation and MapleDoctor can detect and report the schema mismatch.
            4. Use correct {dialect} syntax and functions.
            5. Return ONLY the raw SQL query string without any markdown fences, backticks, or explanations.
            """
            raw_sql = llm.generate_text(prompt).strip()
            if raw_sql.startswith("```sql"):
                raw_sql = raw_sql[6:]
            if raw_sql.startswith("```"):
                raw_sql = raw_sql[3:]
            if raw_sql.endswith("```"):
                raw_sql = raw_sql[:-3]
            raw_sql = raw_sql.strip()

            if not raw_sql.upper().startswith("SELECT") and not raw_sql.upper().startswith("WITH"):
                sel_idx = raw_sql.upper().find("SELECT")
                if sel_idx != -1:
                    raw_sql = raw_sql[sel_idx:].strip()
                else:
                    return self._build_deterministic_sql(schema_context, query_plan, concept_grounding, schema_linking)
            return raw_sql

        except Exception as e:
            print(f"SQLGenerationAgent fallback triggered: {e}")
            return self._build_deterministic_sql(schema_context, query_plan, concept_grounding, schema_linking)

    def propose_action(self, state: GraphState) -> Optional[AgentMessage]:
        if state.sql_candidates:
            return None

        dataset = "spider"
        database_id = state.database_id or state.database

        # 1. DIALECT RESOLUTION via KB
        dialect, dialect_rules = self.dialect_resolver.resolve_dialect(
            dataset=dataset,
            database_id=database_id,
            requested_dialect=state.dialect
        )
        state.dialect = dialect
        if dialect_rules:
            state.knowledge_context["dialect_rules"] = dialect_rules
        dialect_guidelines = self.dialect_resolver.format_guidelines(dialect, dialect_rules)

        # 2. RELATIONAL QUERY PLANNING
        plan = self.planner.create_plan(
            concept_grounding=state.concept_grounding,
            schema_linking=state.schema_linking,
            dialect=dialect
        )
        state.query_plans.append(plan)

        # 3. GENERATE CANDIDATE A (Full/Relevant Schema Context)
        full_schema_ctx = (
            state.schema_linking.full_schema_candidate
            if state.schema_linking and state.schema_linking.full_schema_candidate
            else {"tables": [state.database], "columns": {}}
        )
        sql_a = self._generate_candidate_sql(
            schema_context=full_schema_ctx,
            intent=state.intent,
            dialect=dialect,
            dialect_guidelines=dialect_guidelines,
            query_plan=plan,
            candidate_type="full_schema",
            db_path=state.db_path,
            concept_grounding=state.concept_grounding,
            schema_linking=state.schema_linking
        )
        candidate_a = {
            "id": "candidate_a_full",
            "sql": sql_a,
            "type": "full",
            "confidence": 0.88,
            "schema_tables": full_schema_ctx.get("tables", [])
        }

        # 4. GENERATE CANDIDATE B (Pruned Minimal Schema Context)
        pruned_schema_ctx = (
            state.schema_linking.pruned_schema_candidate
            if state.schema_linking and state.schema_linking.pruned_schema_candidate
            else full_schema_ctx
        )
        sql_b = self._generate_candidate_sql(
            schema_context=pruned_schema_ctx,
            intent=state.intent,
            dialect=dialect,
            dialect_guidelines=dialect_guidelines,
            query_plan=plan,
            candidate_type="pruned_schema",
            db_path=state.db_path,
            concept_grounding=state.concept_grounding,
            schema_linking=state.schema_linking
        )
        candidate_b = {
            "id": "candidate_b_pruned",
            "sql": sql_b,
            "type": "pruned",
            "confidence": 0.92,
            "schema_tables": pruned_schema_ctx.get("tables", [])
        }

        state.sql_candidates = [candidate_a, candidate_b]
        state.selected_candidate = candidate_b  # Default to pruned candidate

        claim_text = f"Generated 2 SQL candidates (Candidate A: full schema, Candidate B: pruned schema) for {dialect} dialect."
        return AgentMessage(
            agent=self.name,
            message_type=MessageType.PROPOSAL,
            capability="Relational Planning & Candidate Generation",
            claim=claim_text,
            evidence=[{"candidate_a": sql_a, "candidate_b": sql_b, "plan": plan}],
            confidence=0.90
        )
