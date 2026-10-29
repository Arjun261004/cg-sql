import sqlite3
from typing import Dict, List, Any

class SQLiteAdapter:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def get_tables(self) -> List[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            return [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]

    def get_schema(self) -> Dict[str, List[Dict[str, str]]]:
        """Returns a dict mapping table names to list of columns with types."""
        schema = {}
        tables = self.get_tables()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for table in tables:
                cursor.execute(f"PRAGMA table_info('{table}');")
                columns = [{"name": row[1], "type": row[2]} for row in cursor.fetchall()]
                schema[table] = columns
        return schema

    def execute_query(self, sql: str) -> Dict[str, Any]:
        """Executes a read-only query and returns status, rows, and data."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                data = cursor.fetchmany(50) # limit fetch for safety/display
                columns = [description[0] for description in cursor.description] if cursor.description else []
                return {
                    "status": "success",
                    "rows": len(data),
                    "columns": columns,
                    "data": data,
                    "error": None
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
