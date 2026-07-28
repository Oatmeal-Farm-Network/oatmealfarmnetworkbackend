# --- data/sql/monitoring_store.py ---
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
from db_control import sql_configured, sql_execute, sql_fetch_all, table_exists

logger = logging.getLogger("farm_advisory.monitoring")

_LOCK = threading.Lock()
_DATA_DIR = str(RUNTIME_DATA_DIR)
_PATH = str(runtime_json_path("saige_monitoring.json"))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _use_sql() -> bool:
    return bool(SAIGE_CONTROL_PLANE_SQL and sql_configured() and table_exists("SaigeMonitoringRuns"))


def _load() -> Dict[str, Any]:
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(_PATH):
        return {"runs": []}
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"runs": []}


def _save(data: Dict[str, Any]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def save_run(
    *,
    business_id: str,
    people_id: str = "",
    thread_id: str = "",
    summary: str = "",
    findings: Optional[List[Dict[str, Any]]] = None,
) -> str:
    run_id = str(uuid.uuid4())
    findings = findings or []

    if _use_sql():
        biz_i = int(business_id) if str(business_id).isdigit() else 0
        people_i = int(people_id) if str(people_id).isdigit() else None
        sql_execute(
            """
            INSERT INTO dbo.SaigeMonitoringRuns (RunID, BusinessID, PeopleID, ThreadID, Summary)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (run_id, biz_i, people_i, thread_id or None, summary or ""),
        )
        if table_exists("SaigeMonitoringFindings"):
            for f in findings:
                fid = f.get("field_id")
                try:
                    fid_i = int(fid) if fid not in (None, "") else None
                except Exception:
                    fid_i = None
                sql_execute(
                    """
                    INSERT INTO dbo.SaigeMonitoringFindings (FindingID, RunID, FieldID, RankScore, FindingText)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        run_id,
                        fid_i,
                        float(f.get("rank") or 0),
                        str(f.get("text") or "")[:4000],
                    ),
                )
        logger.info("[Monitoring] SQL saved run %s", run_id)
        return run_id

    row = {
        "run_id": run_id,
        "business_id": str(business_id or ""),
        "people_id": str(people_id or ""),
        "thread_id": str(thread_id or ""),
        "summary": summary or "",
        "findings": findings,
        "created_at": _utcnow(),
    }
    with _LOCK:
        data = _load()
        data["runs"].append(row)
        _save(data)
    return run_id


def list_runs(*, business_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    if _use_sql():
        where = ["1=1"]
        params: List[Any] = []
        if business_id and str(business_id).isdigit():
            where.append("BusinessID=%s")
            params.append(int(business_id))
        sql = (
            f"SELECT TOP {max(1, int(limit))} * FROM dbo.SaigeMonitoringRuns "
            f"WHERE {' AND '.join(where)} ORDER BY CreatedAt DESC"
        )
        out = []
        for r in sql_fetch_all(sql, tuple(params)):
            rid = str(r.get("RunID") or "")
            findings = []
            if table_exists("SaigeMonitoringFindings"):
                fres = sql_fetch_all(
                    "SELECT * FROM dbo.SaigeMonitoringFindings WHERE RunID=%s ORDER BY RankScore",
                    (rid,),
                )
                findings = [
                    {
                        "rank": f.get("RankScore"),
                        "text": f.get("FindingText"),
                        "field_id": f.get("FieldID"),
                    }
                    for f in fres
                ]
            out.append(
                {
                    "run_id": rid,
                    "business_id": str(r.get("BusinessID") or ""),
                    "people_id": str(r.get("PeopleID") or "") if r.get("PeopleID") is not None else "",
                    "thread_id": r.get("ThreadID") or "",
                    "summary": r.get("Summary") or "",
                    "findings": findings,
                    "created_at": str(r.get("CreatedAt") or ""),
                }
            )
        return out

    with _LOCK:
        rows = list(_load().get("runs") or [])
    if business_id:
        rows = [r for r in rows if r.get("business_id") == str(business_id)]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[:limit]
