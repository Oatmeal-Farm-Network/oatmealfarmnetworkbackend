# --- user_profile.py --- (User name + org membership lookup for Saige)
"""
Fetches the logged-in user's name and their organization's member list from
the OFN SQL Server database. Used to personalise Saige's prompts.

Tables used (read-only):
  People        — PeopleID, PeopleFirstName, PeopleLastName
  BusinessAccess — BusinessID, PeopleID, Active
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, List, Optional

from config import DB_CONFIG

try:
    import pymssql
    _PYMSSQL_OK = True
except ImportError:
    _PYMSSQL_OK = False

logger = logging.getLogger("farm_advisory.user_profile")


def _connect():
    if not _PYMSSQL_OK or not all([
        DB_CONFIG.get("host"), DB_CONFIG.get("user"), DB_CONFIG.get("database")
    ]):
        return None
    try:
        return pymssql.connect(
            server=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            timeout=8,
            login_timeout=8,
        )
    except Exception as e:
        logger.debug("[user_profile] DB connect failed: %s", e)
        return None


def _query(sql: str, params: tuple) -> List[Dict]:
    conn = _connect()
    if not conn:
        return []
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(sql, params)
        return list(cur.fetchall() or [])
    except Exception as e:
        logger.error("[user_profile] query error: %s", e)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_user_name(people_id: str) -> Optional[str]:
    """Return 'FirstName LastName' for a PeopleID, or None if not found/unavailable."""
    if not people_id:
        return None
    rows = _query(
        "SELECT PeopleFirstName, PeopleLastName FROM People WHERE PeopleID = %s",
        (int(people_id),),
    )
    if not rows:
        return None
    first = (rows[0].get("PeopleFirstName") or "").strip()
    last = (rows[0].get("PeopleLastName") or "").strip()
    full = f"{first} {last}".strip()
    return full or None


def get_org_member_ids(business_id: str) -> List[str]:
    """Return list of PeopleID strings for all active members of a business/org."""
    if not business_id:
        return []
    rows = _query(
        "SELECT PeopleID FROM BusinessAccess WHERE BusinessID = %s AND Active = 1",
        (int(business_id),),
    )
    return [str(r["PeopleID"]) for r in rows if r.get("PeopleID")]


def get_business_name(business_id: str) -> Optional[str]:
    """Return the BusinessName for a given BusinessID, or None if not found."""
    if not business_id:
        return None
    rows = _query(
        "SELECT BusinessName FROM Business WHERE BusinessID = %s",
        (int(business_id),),
    )
    if not rows:
        return None
    name = rows[0].get("BusinessName") or rows[0].get("businessname")
    return str(name).strip() if name else None


def get_primary_business_id(people_id: str) -> Optional[str]:
    """Return the first active BusinessID for this PeopleID, or None if none found."""
    if not people_id:
        return None
    rows = _query(
        "SELECT TOP 1 BusinessID FROM BusinessAccess WHERE PeopleID = %s AND Active = 1 ORDER BY BusinessID",
        (int(people_id),),
    )
    if not rows:
        return None
    bid = rows[0].get("BusinessID") or rows[0].get("businessid")
    return str(bid) if bid else None


def get_org_member_names(business_id: str) -> Dict[str, str]:
    """Return {people_id: 'First Last'} for all active org members."""
    if not business_id:
        return {}
    rows = _query(
        """
        SELECT p.PeopleID, p.PeopleFirstName, p.PeopleLastName
        FROM BusinessAccess ba
        JOIN People p ON ba.PeopleID = p.PeopleID
        WHERE ba.BusinessID = %s AND ba.Active = 1
        """,
        (int(business_id),),
    )
    result: Dict[str, str] = {}
    for r in rows:
        pid = str(r.get("PeopleID") or "")
        first = (r.get("PeopleFirstName") or "").strip()
        last = (r.get("PeopleLastName") or "").strip()
        name = f"{first} {last}".strip()
        if pid and name:
            result[pid] = name
    return result
