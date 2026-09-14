# --- data/sql/control.py ---
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

from data.sql.connect import sql_configured, sql_connect

logger = logging.getLogger("farm_advisory.db_control")

__all__ = [
    "sql_configured",
    "sql_conn",
    "sql_execute",
    "sql_fetch_all",
    "sql_fetch_one",
    "table_exists",
]


@contextmanager
def sql_conn() -> Iterator[Any]:
    conn = sql_connect(as_dict=True, timeout=30, login_timeout=8)
    if conn is None:
        raise RuntimeError("SQL is not configured")
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def sql_execute(sql: str, params: Tuple[Any, ...] = ()) -> int:
    with sql_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return int(getattr(cur, "rowcount", 0) or 0)


def sql_fetch_all(sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    with sql_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]


def sql_fetch_one(sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
    rows = sql_fetch_all(sql, params)
    return rows[0] if rows else None


def table_exists(table_name: str) -> bool:
    if not sql_configured():
        return False
    try:
        row = sql_fetch_one(
            "SELECT 1 AS ok FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=%s",
            (table_name,),
        )
        return bool(row)
    except Exception as e:
        logger.debug("[db_control] table_exists(%s) failed: %s", table_name, e)
        return False
