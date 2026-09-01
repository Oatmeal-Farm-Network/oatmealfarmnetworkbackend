# --- data/sql/connect.py ---
"""Shared SQL Server connections for Saige.

Local/dev uses pymssql against DB_HOST (or DB_SERVER). Cloud Run staging/prod
must use the Cloud SQL Python Connector + pytds: SQL Server does not get a
127.0.0.1:1433 Auth Proxy listener even with --set-cloudsql-instances.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Sequence

from config import DB_CONFIG

logger = logging.getLogger("farm_advisory.sql")

_connector = None


def instance_connection_name() -> str:
    return (os.getenv("INSTANCE_CONNECTION_NAME") or "").strip()


def sql_configured() -> bool:
    """True when credentials exist for either Connector or direct pymssql."""
    user = (DB_CONFIG.get("user") or "").strip()
    database = (DB_CONFIG.get("database") or "").strip()
    if not user or not database:
        return False
    if instance_connection_name():
        return True
    return bool((DB_CONFIG.get("host") or "").strip())


def _get_connector():
    global _connector
    if _connector is None:
        from google.cloud.sql.connector import Connector, IPTypes

        ip_type = IPTypes.PRIVATE if os.getenv("PRIVATE_IP") else IPTypes.PUBLIC
        _connector = Connector(ip_type=ip_type, refresh_strategy="LAZY")
    return _connector


def _connect_raw(*, timeout: int = 30, login_timeout: int = 15):
    user = DB_CONFIG.get("user")
    password = DB_CONFIG.get("password")
    database = DB_CONFIG.get("database")
    instance = instance_connection_name()
    if instance:
        return _get_connector().connect(
            instance,
            "pytds",
            user=user,
            password=password,
            db=database,
        )
    import pymssql

    return pymssql.connect(
        server=DB_CONFIG["host"],
        port=int(DB_CONFIG.get("port") or 1433),
        user=user,
        password=password,
        database=database,
        timeout=timeout,
        login_timeout=login_timeout,
    )


def rows_as_dicts(cursor, rows: Sequence[Any], *, as_dict: bool) -> List[Any]:
    """Normalize fetch results to dicts with original + lowercase keys."""
    if not as_dict:
        return list(rows or [])
    out: List[Dict[str, Any]] = []
    description = getattr(cursor, "description", None)
    colnames: List[str] = []
    if description:
        colnames = [str(col[0]) for col in description]
    for row in rows or []:
        if row is None:
            continue
        if isinstance(row, dict):
            mapped = dict(row)
        else:
            mapped = {}
            values = list(row)
            for i, val in enumerate(values):
                key = colnames[i] if i < len(colnames) else str(i)
                mapped[key] = val
        aliased = dict(mapped)
        for key, val in mapped.items():
            aliased[str(key).lower()] = val
        out.append(aliased)
    return out


class _Cursor:
    def __init__(self, cursor, as_dict: bool):
        self._c = cursor
        self._as_dict = as_dict

    def execute(self, sql, params=None):
        if params in (None, ()):
            return self._c.execute(sql)
        return self._c.execute(sql, params)

    def fetchall(self):
        rows = self._c.fetchall() or []
        return rows_as_dicts(self._c, rows, as_dict=self._as_dict)

    def fetchone(self):
        row = self._c.fetchone()
        if row is None:
            return None
        rows = rows_as_dicts(self._c, [row], as_dict=self._as_dict)
        return rows[0] if rows else None

    def close(self):
        close = getattr(self._c, "close", None)
        if close:
            close()

    def __getattr__(self, name):
        return getattr(self._c, name)


class SqlConnection:
    """Thin wrapper so pymssql-style cursor(as_dict=True) works with pytds."""

    def __init__(self, raw, default_as_dict: bool = False):
        self._raw = raw
        self._default_as_dict = default_as_dict

    def cursor(self, *args, **kwargs):
        as_dict = kwargs.pop("as_dict", None)
        if as_dict is None:
            as_dict = self._default_as_dict
        raw_cur = None
        if as_dict:
            try:
                raw_cur = self._raw.cursor(as_dict=True, *args, **kwargs)
            except TypeError:
                raw_cur = None
        if raw_cur is None:
            raw_cur = self._raw.cursor(*args, **kwargs)
        return _Cursor(raw_cur, bool(as_dict))

    def close(self):
        self._raw.close()

    def commit(self):
        commit = getattr(self._raw, "commit", None)
        if commit:
            commit()

    def rollback(self):
        rollback = getattr(self._raw, "rollback", None)
        if rollback:
            rollback()

    def __getattr__(self, name):
        return getattr(self._raw, name)


def sql_connect(
    *,
    as_dict: bool = False,
    timeout: int = 30,
    login_timeout: int = 15,
) -> Optional[SqlConnection]:
    if not sql_configured():
        return None
    try:
        raw = _connect_raw(timeout=timeout, login_timeout=login_timeout)
        return SqlConnection(raw, default_as_dict=as_dict)
    except Exception as e:
        logger.warning("SQL connect failed: %s", e)
        print(f"[sql] connect failed: {e}")
        return None
