# --- services/user_profile.py ---
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
from typing import Any, Dict, List, Optional

from config import DB_CONFIG

try:
    import pymssql
    _PYMSSQL_OK = True
except ImportError:
    _PYMSSQL_OK = False

logger = logging.getLogger("farm_advisory.user_profile")


def _row_get(row: Optional[Dict], *keys: str, default: Any = None) -> Any:
    """Read a SQL row value with case-insensitive key matching (FreeTDS may lowercase)."""
    if not row:
        return default
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
        val = lower_map.get(str(key).lower())
        if val is not None:
            return val
    return default


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
    first = str(_row_get(rows[0], "PeopleFirstName", "peoplefirstname") or "").strip()
    last = str(_row_get(rows[0], "PeopleLastName", "peoplelastname") or "").strip()
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
    out = []
    for r in rows:
        pid = _row_get(r, "PeopleID", "peopleid")
        if pid is not None:
            out.append(str(pid))
    return out


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
    name = _row_get(rows[0], "BusinessName", "businessname")
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
    bid = _row_get(rows[0], "BusinessID", "businessid")
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
        pid = str(_row_get(r, "PeopleID", "peopleid") or "")
        first = str(_row_get(r, "PeopleFirstName", "peoplefirstname") or "").strip()
        last = str(_row_get(r, "PeopleLastName", "peoplelastname") or "").strip()
        name = f"{first} {last}".strip()
        if pid and name:
            result[pid] = name
    return result


def get_account_profile(people_id: str, business_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Read account + optional business profile fields for Saige User Agent.
    NEVER returns password / hash / secret columns.
    """
    profile: Dict[str, Any] = {}
    if not people_id:
        return profile

    rows = _query(
        """
        SELECT PeopleID, PeopleFirstName, PeopleLastName, PeopleEmail, PeoplePhone
        FROM People
        WHERE PeopleID = %s
        """,
        (int(people_id),),
    )
    if not rows:
        # Name-only fallback if email/phone columns unavailable on this DB
        rows = _query(
            """
            SELECT PeopleID, PeopleFirstName, PeopleLastName
            FROM People
            WHERE PeopleID = %s
            """,
            (int(people_id),),
        )
    if rows:
        r = rows[0]
        profile = {
            "people_id": str(_row_get(r, "PeopleID", "peopleid") or people_id),
            "first_name": str(_row_get(r, "PeopleFirstName", "peoplefirstname") or "").strip(),
            "last_name": str(_row_get(r, "PeopleLastName", "peoplelastname") or "").strip(),
        }
        email = _row_get(r, "PeopleEmail", "peopleemail")
        if email:
            profile["email"] = str(email).strip()
        phone = _row_get(r, "PeoplePhone", "peoplephone")
        if phone:
            profile["phone"] = str(phone).strip()

    profile = {k: v for k, v in profile.items() if "password" not in k.lower() and "hash" not in k.lower()}

    bid = business_id or get_primary_business_id(people_id)
    if bid:
        profile["business_id"] = str(bid)
        bname = get_business_name(bid)
        if bname:
            profile["business_name"] = bname
        # Fall back to business contact email when personal email is missing
        if not profile.get("email"):
            brows = _query(
                "SELECT BusinessEmail FROM Business WHERE BusinessID = %s",
                (int(bid),),
            )
            if brows:
                bem = _row_get(brows[0], "BusinessEmail", "businessemail")
                if bem:
                    profile["email"] = str(bem).strip()
                    profile["email_source"] = "business"
    return profile
