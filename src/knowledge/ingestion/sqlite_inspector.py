import sqlite3
from typing import List, Dict, Any, Optional

class SQLiteInspector:
    """
    Extracts metadata and statistics directly from a SQLite database file.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None

    def __enter__(self):
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            self._conn.close()

    def get_tables(self) -> List[str]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        return [row['name'] for row in cursor.fetchall()]

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        cursor.execute(f"PRAGMA table_info(`{table_name}`);")
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "name": row['name'],
                "type": row['type'],
                "nullable": not bool(row['notnull']),
                "default_value": row['dflt_value'],
                "is_primary_key": bool(row['pk'])
            })
        return columns

    def get_foreign_keys(self, table_name: str) -> List[Dict[str, str]]:
        cursor = self._conn.cursor()
        # PRAGMA foreign_key_list returns: id, seq, table, from, to, on_update, on_delete, match
        cursor.execute(f"PRAGMA foreign_key_list(`{table_name}`);")
        fks = []
        for row in cursor.fetchall():
            fks.append({
                "column": row['from'],
                "target_table": row['table'],
                "target_column": row['to']
            })
        return fks

    def get_row_count(self, table_name: str) -> int:
        cursor = self._conn.cursor()
        try:
            cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table_name}`;")
            return cursor.fetchone()['cnt']
        except sqlite3.OperationalError:
            return 0

    def get_column_statistics(self, table_name: str, column_name: str, sample_limit: int = 5) -> Dict[str, Any]:
        cursor = self._conn.cursor()
        stats = {}
        try:
            # Null count
            cursor.execute(f"SELECT COUNT(*) as null_cnt FROM `{table_name}` WHERE `{column_name}` IS NULL;")
            stats['null_count'] = cursor.fetchone()['null_cnt']
            
            # Distinct count
            cursor.execute(f"SELECT COUNT(DISTINCT `{column_name}`) as dist_cnt FROM `{table_name}`;")
            stats['distinct_count'] = cursor.fetchone()['dist_cnt']
            
            # Sample values (non-null)
            cursor.execute(f"SELECT DISTINCT `{column_name}` as val FROM `{table_name}` WHERE `{column_name}` IS NOT NULL LIMIT {sample_limit};")
            stats['sample_values'] = [row['val'] for row in cursor.fetchall()]
            
            # Min/Max (only useful if numeric/date, but sqlite is typeless so we just try)
            cursor.execute(f"SELECT MIN(`{column_name}`) as min_val, MAX(`{column_name}`) as max_val FROM `{table_name}`;")
            row = cursor.fetchone()
            stats['min_value'] = row['min_val']
            stats['max_value'] = row['max_val']
            
        except sqlite3.OperationalError:
            pass
            
        return stats
