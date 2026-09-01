# --- data/sql/database.py ---
import re
from typing import List, Dict

from config import ALLOWED_TABLES
from data.sql.connect import sql_connect, sql_configured


class Database:
    """Manages database connections and queries for livestock data."""

    def __init__(self):
        self._connection = None
        self._allowed_tables = [t.lower() for t in ALLOWED_TABLES]

    @property
    def connection(self):
        """Lazy connection to database."""
        if self._connection is None and sql_configured():
            try:
                self._connection = sql_connect(as_dict=True)
                if self._connection is not None:
                    print("[DB] Connected")
            except Exception as e:
                print(f"[DB] Connection failed: {e}")
        return self._connection

    def _validate_query(self, query: str) -> None:
        """Validate query only accesses allowed tables."""
        query_lower = query.lower()
        tables = re.findall(r'from\s+\[?(\w+)\]?', query_lower)
        tables += re.findall(r'join\s+\[?(\w+)\]?', query_lower)
        for table in tables:
            if table not in self._allowed_tables:
                raise PermissionError(f"Access denied to table: {table}")

    def fetch_all(self, table: str) -> List[Dict]:
        """Fetch all rows from an allowed table."""
        if table.lower() not in self._allowed_tables:
            raise PermissionError(f"Access denied to table: {table}")
        if not self.connection:
            return []
        try:
            cursor = self.connection.cursor()
            cursor.execute(f"SELECT * FROM [{table}]")
            return cursor.fetchall() or []
        except Exception as e:
            print(f"[DB] fetch_all({table}) error: {e}")
            return []

    def execute(self, query: str) -> List[Dict]:
        """Execute a SELECT query and return results."""
        if not self.connection:
            return []
        try:
            self._validate_query(query)
            cursor = self.connection.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            return results if results else []
        except Exception as e:
            print(f"[DB] Query error: {e}")
            return []


db = Database()
