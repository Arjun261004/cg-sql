import re
from typing import Dict, List, Any, Optional

class NLPIntentParser:
    """
    Deterministic NLP Intent Parser tool for QueryUnderstandingAgent.
    Extracts semantic intent, limits, aggregations, sort orders, and temporal constraints.
    """
    def __init__(self):
        pass

    def parse_intent(self, query: str) -> Dict[str, Any]:
        raw_query = (query or "").strip()
        normalized_query = re.sub(r'[^\w\s\d]', ' ', raw_query.lower())
        normalized_query = re.sub(r'\s+', ' ', normalized_query).strip()

        aggregations: List[str] = []
        sorting_requirements: List[Dict[str, Any]] = []
        temporal_constraints: List[str] = []
        filters: List[Dict[str, Any]] = []
        limits: Optional[int] = None

        # 1. Extract Limits (e.g. "top 5", "first 10", "limit 3")
        limit_match = re.search(r'\b(?:top|first|limit)\s+(\d+)\b', raw_query, re.IGNORECASE)
        if limit_match:
            limits = int(limit_match.group(1))

        # 2. Extract Sorting / Ranking
        if re.search(r'\b(?:highest|most|maximum|greatest|best|top|descending)\b', raw_query, re.IGNORECASE):
            sorting_requirements.append({"direction": "DESC", "metric": "target_metric"})
        elif re.search(r'\b(?:lowest|least|minimum|smallest|worst|ascending)\b', raw_query, re.IGNORECASE):
            sorting_requirements.append({"direction": "ASC", "metric": "target_metric"})

        # 3. Extract Aggregations
        if re.search(r'\b(?:how many|number of|count)\b', raw_query, re.IGNORECASE):
            aggregations.append("COUNT")
        if re.search(r'\b(?:total|sum)\b', raw_query, re.IGNORECASE):
            aggregations.append("SUM")
        if re.search(r'\b(?:average|avg|mean)\b', raw_query, re.IGNORECASE):
            aggregations.append("AVG")
        if re.search(r'\b(?:highest|maximum|max)\b', raw_query, re.IGNORECASE):
            aggregations.append("MAX")
        if re.search(r'\b(?:lowest|minimum|min)\b', raw_query, re.IGNORECASE):
            aggregations.append("MIN")

        # 4. Extract Temporal Constraints
        years = re.findall(r'\b(20\d\d|19\d\d)\b', raw_query)
        for y in years:
            temporal_constraints.append(y)
            filters.append({"field": "year", "op": "=", "value": y})
        if re.search(r'\bmonthly\b', raw_query, re.IGNORECASE):
            temporal_constraints.append("monthly")
        if re.search(r'\bannual|yearly\b', raw_query, re.IGNORECASE):
            temporal_constraints.append("yearly")

        # 5. Extract Range Filters (e.g. "age between 30 and 40")
        between_match = re.search(
            r'\b(?:of\s+)?([a-zA-Z_]+)\s+(?:of\s+)?between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)\b',
            raw_query,
            re.IGNORECASE
        )
        if between_match:
            f_name = between_match.group(1).lower()
            val1 = float(between_match.group(2)) if '.' in between_match.group(2) else int(between_match.group(2))
            val2 = float(between_match.group(3)) if '.' in between_match.group(3) else int(between_match.group(3))
            filters.append({"field": f_name, "op": "BETWEEN", "value": [val1, val2]})
        else:
            between_match2 = re.search(
                r'\b([a-zA-Z_]+)\b[^\w\d]+between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)\b',
                raw_query,
                re.IGNORECASE
            )
            if between_match2:
                f_candidate = between_match2.group(1).lower()
                if f_candidate not in ["show", "all", "select", "find", "get", "list", "the"]:
                    val1 = float(between_match2.group(2)) if '.' in between_match2.group(2) else int(between_match2.group(2))
                    val2 = float(between_match2.group(3)) if '.' in between_match2.group(3) else int(between_match2.group(3))
                    filters.append({"field": f_candidate, "op": "BETWEEN", "value": [val1, val2]})

        # 6. Extract Comparison Operators (>=, <=, >, <)
        comp_patterns = [
            (r'\b([a-zA-Z_]+)\s*(?:>=|at least)\s*(\d+(?:\.\d+)?)\b', ">="),
            (r'\b([a-zA-Z_]+)\s*(?:<=|at most)\s*(\d+(?:\.\d+)?)\b', "<="),
            (r'\b([a-zA-Z_]+)\s*(?:>|greater than|older than|above|more than)\s*(\d+(?:\.\d+)?)\b', ">"),
            (r'\b([a-zA-Z_]+)\s*(?:<|less than|younger than|below|under)\s*(\d+(?:\.\d+)?)\b', "<"),
        ]
        for pat, op in comp_patterns:
            m = re.search(pat, raw_query, re.IGNORECASE)
            if m:
                f_field = m.group(1).lower()
                if f_field not in ["show", "all", "select", "find", "get", "list", "where", "with", "the"]:
                    val = float(m.group(2)) if '.' in m.group(2) else int(m.group(2))
                    if not any(f.get("field") == f_field for f in filters):
                        filters.append({"field": f_field, "op": op, "value": val})

        # 7. Extract Categorical / String Equality Filters (e.g. "with course science")
        with_match = re.search(
            r'\b(?:with|where|having)\s+([a-zA-Z_]+)\s+(?:is\s+|equal\s+to\s+|=)?([\'"]?[a-zA-Z0-9_]+[\'"]?)\b',
            raw_query,
            re.IGNORECASE
        )
        if with_match:
            f_field = with_match.group(1).lower()
            f_val = with_match.group(2).strip("'\"")
            if f_field not in ["show", "all", "select", "find", "get", "list", "where", "with", "between", "the"]:
                if not any(f.get("field") == f_field for f in filters):
                    filters.append({"field": f_field, "op": "=", "value": f_val})

        return {
            "raw_query": raw_query,
            "normalized_query": normalized_query,
            "aggregations": aggregations,
            "sorting_requirements": sorting_requirements,
            "temporal_constraints": temporal_constraints,
            "filters": filters,
            "limits": limits,
            "comparison_requirements": []
        }
