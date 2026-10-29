from typing import Dict, List, Any, Optional

class DatabaseProber:
    """
    Lightweight, read-only database probing component for MapleDoctor.
    Executes surgical inspection queries to check:
    - Value-overlap in JOIN conditions (Algorithm 1 / Rule 9)
    - Subquery row counts (= vs IN / Rule 7)
    - NULL existence in columns (Ascending Sort with NULL / Rule 8)
    - Sample values for text/numeric checks (Rule 11)
    - Distinct values for enumeration specification (Rule 10)
    All operations are strictly read-only with tight LIMIT bounds.
    """
    def __init__(self, executor: Optional[Any] = None):
        if executor is None:
            from src.tools.database_executor import DatabaseExecutor
            self.executor = DatabaseExecutor()
        else:
            self.executor = executor

    def probe_value_overlap(
        self,
        left_table: str,
        left_col: str,
        right_table: str,
        right_col: str,
        dialect: str = "SQLite",
        db_path: str = "",
        dataset: str = "spider",
        database_id: str = "default"
    ) -> bool:
        """
        Paper Algorithm 1: Value overlap probe.
        Checks if: SELECT 1 FROM left_table JOIN right_table ON left_table.col1 = right_table.col2 LIMIT 1
        returns any row. Returns True if overlap exists, False if EMPTY (0 rows).
        """
        probe_sql = (
            f"SELECT 1 FROM {left_table} JOIN {right_table} "
            f"ON {left_table}.{left_col} = {right_table}.{right_col} LIMIT 1"
        )
        try:
            res = self.executor.execute(
                sql=probe_sql,
                dialect=dialect,
                db_path=db_path,
                dataset=dataset,
                database_id=database_id
            )
            return res.get("status") == "success" and res.get("rows", 0) > 0
        except Exception:
            return True  # Be conservative on probe error

    def probe_subquery_row_count(
        self,
        subquery_sql: str,
        dialect: str = "SQLite",
        db_path: str = "",
        dataset: str = "spider",
        database_id: str = "default"
    ) -> int:
        """
        Executes subquery with LIMIT 2 to determine if it can return > 1 row.
        Returns estimated row count (0, 1, or 2+).
        """
        clean_subquery = subquery_sql.strip().rstrip(";")
        probe_sql = f"SELECT COUNT(*) as cnt FROM ({clean_subquery}) AS _probe_subq"
        try:
            res = self.executor.execute(
                sql=probe_sql,
                dialect=dialect,
                db_path=db_path,
                dataset=dataset,
                database_id=database_id
            )
            if res.get("status") == "success" and res.get("data"):
                return int(res["data"][0][0])
            return 0
        except Exception:
            return 1

    def probe_column_has_nulls(
        self,
        table_name: str,
        col_name: str,
        dialect: str = "SQLite",
        db_path: str = "",
        dataset: str = "spider",
        database_id: str = "default"
    ) -> bool:
        """
        Rule 8: Ascending sort with NULL probe.
        Checks if: SELECT 1 FROM table WHERE col IS NULL LIMIT 1
        returns any row.
        """
        probe_sql = f"SELECT 1 FROM {table_name} WHERE {col_name} IS NULL LIMIT 1"
        try:
            res = self.executor.execute(
                sql=probe_sql,
                dialect=dialect,
                db_path=db_path,
                dataset=dataset,
                database_id=database_id
            )
            return res.get("status") == "success" and res.get("rows", 0) > 0
        except Exception:
            return False

    def probe_sample_values(
        self,
        table_name: str,
        col_name: str,
        limit: int = 10,
        dialect: str = "SQLite",
        db_path: str = "",
        dataset: str = "spider",
        database_id: str = "default"
    ) -> List[Any]:
        """
        Rule 11: Sample value retrieval for aggregation/comparison checks.
        """
        probe_sql = f"SELECT {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL LIMIT {limit}"
        try:
            res = self.executor.execute(
                sql=probe_sql,
                dialect=dialect,
                db_path=db_path,
                dataset=dataset,
                database_id=database_id
            )
            if res.get("status") == "success" and res.get("data"):
                return [row[0] for row in res["data"]]
            return []
        except Exception:
            return []

    def probe_distinct_values(
        self,
        table_name: str,
        col_name: str,
        limit: int = 50,
        dialect: str = "SQLite",
        db_path: str = "",
        dataset: str = "spider",
        database_id: str = "default"
    ) -> List[Any]:
        """
        Rule 10: Distinct values probe for enumeration specification check.
        """
        probe_sql = f"SELECT DISTINCT {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL LIMIT {limit}"
        try:
            res = self.executor.execute(
                sql=probe_sql,
                dialect=dialect,
                db_path=db_path,
                dataset=dataset,
                database_id=database_id
            )
            if res.get("status") == "success" and res.get("data"):
                return [row[0] for row in res["data"]]
            return []
        except Exception:
            return []
