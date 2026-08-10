# --- data/sql/plans_store.py ---
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import SAIGE_CONTROL_PLANE_SQL
from core.paths import RUNTIME_DATA_DIR, runtime_json_path
from db_control import sql_configured, sql_execute, sql_fetch_all, sql_fetch_one, table_exists

logger = logging.getLogger("farm_advisory.plans")

_LOCK = threading.Lock()
_DATA_DIR = str(RUNTIME_DATA_DIR)
_PATH = str(runtime_json_path("saige_plans.json"))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _use_sql() -> bool:
    return bool(SAIGE_CONTROL_PLANE_SQL and sql_configured() and table_exists("SaigePlans"))


def _load() -> Dict[str, Any]:
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(_PATH):
        return {"plans": []}
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"plans": []}


def _save(data: Dict[str, Any]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def save_plan(
    *,
    business_id: str,
    people_id: str = "",
    title: str = "Farm plan",
    items: Optional[List[Dict[str, Any]]] = None,
    status: str = "draft",
) -> str:
    plan_id = str(uuid.uuid4())
    now = _utcnow()
    items = items or []

    if _use_sql():
        biz_i = int(business_id) if str(business_id).isdigit() else 0
        people_i = int(people_id) if str(people_id).isdigit() else None
        sql_execute(
            """
            INSERT INTO dbo.SaigePlans (PlanID, BusinessID, PeopleID, Title, Status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (plan_id, biz_i, people_i, (title or "Farm plan")[:200], status or "draft"),
        )
        if table_exists("SaigePlanItems"):
            for it in items:
                sql_execute(
                    """
                    INSERT INTO dbo.SaigePlanItems (PlanItemID, PlanID, DueDate, TaskText, Domain, Status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        plan_id,
                        it.get("date") or it.get("due_date"),
                        (it.get("task") or it.get("task_text") or "")[:500],
                        (it.get("domain") or "")[:64],
                        it.get("status") or "open",
                    ),
                )
        logger.info("[Plans] SQL saved %s", plan_id)
        return plan_id

    row = {
        "plan_id": plan_id,
        "business_id": str(business_id or ""),
        "people_id": str(people_id or ""),
        "title": title or "Farm plan",
        "status": status,
        "items": items,
        "created_at": now,
        "updated_at": now,
    }
    with _LOCK:
        data = _load()
        data["plans"].append(row)
        _save(data)
    return plan_id


def _items_for_plan(plan_id: str) -> List[Dict[str, Any]]:
    if not table_exists("SaigePlanItems"):
        return []
    rows = sql_fetch_all(
        "SELECT * FROM dbo.SaigePlanItems WHERE PlanID=%s ORDER BY DueDate",
        (plan_id,),
    )
    return [
        {
            "date": str(r.get("DueDate") or ""),
            "task": r.get("TaskText") or "",
            "domain": r.get("Domain") or "",
            "status": r.get("Status") or "open",
        }
        for r in rows
    ]


def list_plans(
    *,
    business_id: Optional[str] = None,
    people_id: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    if _use_sql():
        where = ["1=1"]
        params: List[Any] = []
        if business_id and str(business_id).isdigit():
            where.append("BusinessID=%s")
            params.append(int(business_id))
        if people_id and str(people_id).isdigit():
            where.append("PeopleID=%s")
            params.append(int(people_id))
        sql = (
            f"SELECT TOP {max(1, int(limit))} * FROM dbo.SaigePlans "
            f"WHERE {' AND '.join(where)} ORDER BY CreatedAt DESC"
        )
        out = []
        for r in sql_fetch_all(sql, tuple(params)):
            pid = str(r.get("PlanID") or "")
            out.append(
                {
                    "plan_id": pid,
                    "business_id": str(r.get("BusinessID") or ""),
                    "people_id": str(r.get("PeopleID") or "") if r.get("PeopleID") is not None else "",
                    "title": r.get("Title") or "",
                    "status": r.get("Status") or "",
                    "items": _items_for_plan(pid),
                    "created_at": str(r.get("CreatedAt") or ""),
                    "updated_at": str(r.get("UpdatedAt") or ""),
                }
            )
        return out

    with _LOCK:
        rows = list(_load().get("plans") or [])
    if business_id:
        rows = [r for r in rows if r.get("business_id") == str(business_id)]
    if people_id:
        rows = [r for r in rows if r.get("people_id") == str(people_id)]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[:limit]


def get_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    if _use_sql():
        r = sql_fetch_one("SELECT * FROM dbo.SaigePlans WHERE PlanID=%s", (plan_id,))
        if not r:
            return None
        return {
            "plan_id": plan_id,
            "business_id": str(r.get("BusinessID") or ""),
            "people_id": str(r.get("PeopleID") or "") if r.get("PeopleID") is not None else "",
            "title": r.get("Title") or "",
            "status": r.get("Status") or "",
            "items": _items_for_plan(plan_id),
            "created_at": str(r.get("CreatedAt") or ""),
            "updated_at": str(r.get("UpdatedAt") or ""),
        }
    with _LOCK:
        for r in _load().get("plans") or []:
            if r.get("plan_id") == plan_id:
                return r
    return None
