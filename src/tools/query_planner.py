from typing import Dict, List, Any, Optional
from src.models.state import ConceptGroundingResult, SchemaLinkingResult

class QueryPlanner:
    """
    Internal Relational Query Planner for SQLGenerationAgent.
    Constructs a relational execution plan (filtering, joins, aggregations,
    grouping, ordering, limits, and CTE decomposition) prior to SQL generation.
    """
    def create_plan(
        self,
        concept_grounding: Optional[ConceptGroundingResult],
        schema_linking: Optional[SchemaLinkingResult],
        dialect: str = "SQLite"
    ) -> Dict[str, Any]:
        """Creates a structured relational execution plan."""
        steps: List[str] = []
        base_tables = schema_linking.final_tables if schema_linking else []
        
        # Step 1: Base table selection
        if base_tables:
            steps.append(f"Select from primary table: {base_tables[0]}")
        else:
            steps.append("Identify base table from user request")

        # Step 2: Filtering
        filters = []
        if concept_grounding and concept_grounding.filters:
            for f in concept_grounding.filters:
                filters.append(f)
                op = f.get("op", "=").upper()
                val = f.get("value", "")
                field = f.get("field", "condition")
                if op == "BETWEEN" and isinstance(val, (list, tuple)) and len(val) == 2:
                    steps.append(f"Filter rows where {field} BETWEEN {val[0]} AND {val[1]}")
                else:
                    steps.append(f"Filter rows where {field} {op} {val}")
        if concept_grounding and concept_grounding.temporal_constraints:
            for t in concept_grounding.temporal_constraints:
                steps.append(f"Apply temporal filter: {t}")

        # Step 3: Joins
        joins = []
        if schema_linking and schema_linking.join_paths:
            for path in schema_linking.join_paths:
                for rel in path:
                    rel_dict = rel if isinstance(rel, dict) else rel.dict()
                    joins.append(rel_dict)
                    steps.append(
                        f"Join {rel_dict.get('source_table')} and {rel_dict.get('target_table')} "
                        f"ON {rel_dict.get('source_table')}.{rel_dict.get('source_column')} = "
                        f"{rel_dict.get('target_table')}.{rel_dict.get('target_column')}"
                    )

        # Step 4: Aggregation and Grouping
        aggregations = []
        group_by = []
        if concept_grounding:
            aggregations = concept_grounding.aggregations
            if aggregations:
                steps.append(f"Aggregate metrics using: {', '.join(aggregations)}")
                if concept_grounding.dimensions:
                    group_by = concept_grounding.dimensions
                    steps.append(f"Group by dimensions: {', '.join(group_by)}")

        # Step 5: Sorting and Limit
        sorting = []
        limit = None
        if concept_grounding:
            sorting = concept_grounding.sorting_requirements
            limit = concept_grounding.limits
            if sorting:
                steps.append(f"Sort results: {sorting}")
            if limit:
                steps.append(f"Apply limit: {limit}")

        # Complex query check: decompose into CTEs if multi-stage
        cte_plan = []
        if len(joins) > 1 or (aggregations and sorting):
            cte_plan = [
                {"name": "filtered_records", "purpose": "Apply filters and join base tables"},
                {"name": "aggregated_metrics", "purpose": "Calculate aggregations and grouping"},
                {"name": "final_select", "purpose": "Order and limit final result set"}
            ]

        return {
            "steps": steps,
            "base_tables": base_tables,
            "filters": filters,
            "joins": joins,
            "aggregations": aggregations,
            "group_by": group_by,
            "sorting": sorting,
            "limit": limit,
            "cte_plan": cte_plan,
            "dialect": dialect
        }

