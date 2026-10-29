import re
from typing import List, Dict, Any, Tuple
from src.knowledge.core.models import DatabaseSchema, TableSchema, ColumnSchema

class SchemaSearch:
    """
    Deterministic schema search using token matching.
    """
    def __init__(self, schema: DatabaseSchema):
        self.schema = schema
        
    def _tokenize(self, text: str) -> set:
        # Split by non-alphanumeric, convert to lowercase
        tokens = re.split(r'[^a-zA-Z0-9]+', text.lower())
        return {t for t in tokens if len(t) > 2} # ignore very short words like 'a', 'is'

    def search(self, query: str) -> Dict[str, Any]:
        """
        Rank tables and columns by token overlap with the query.
        Returns top tables and columns.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return {"tables": [], "columns": []}

        table_scores: List[Tuple[float, TableSchema]] = []
        column_scores: List[Tuple[float, str, ColumnSchema]] = [] # (score, table_name, column)

        for table_name, table in self.schema.tables.items():
            # Score table
            table_tokens = self._tokenize(table_name)
            t_overlap = len(query_tokens.intersection(table_tokens))
            t_score = t_overlap / max(len(query_tokens), 1)
            
            if t_score > 0:
                table_scores.append((t_score, table))

            # Score columns
            for col_name, col in table.columns.items():
                col_tokens = self._tokenize(col_name)
                c_overlap = len(query_tokens.intersection(col_tokens))
                c_score = c_overlap / max(len(query_tokens), 1)
                
                # Boost if table also matches
                if t_overlap > 0 and c_overlap > 0:
                    c_score += 0.2
                    
                if c_score > 0:
                    column_scores.append((c_score, table_name, col))

        # Sort descending by score
        table_scores.sort(key=lambda x: x[0], reverse=True)
        column_scores.sort(key=lambda x: x[0], reverse=True)

        return {
            "tables": [{"name": t.name, "score": s} for s, t in table_scores[:5]],
            "columns": [{"table": tn, "name": c.name, "score": s} for s, tn, c in column_scores[:10]]
        }
