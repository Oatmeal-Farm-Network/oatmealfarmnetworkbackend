# --- data/sql/proposals_store.py ---
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

logger = logging.getLogger("farm_advisory.proposals")

_LOCK = threading.Lock()
_DATA_DIR = str(RUNTIME_DATA_DIR)
_JSON_PATH = str(runtime_json_path("saige_proposals.json"))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _use_sql() -> bool:
    return bool(SAIGE_CONTROL_PLANE_SQL and sql_configured() and table_exists("SaigeProposals"))


def _ensure_json() -> Dict[str, Any]:
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(_JSON_PATH):
        return {"proposals": [], "events": []}
    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"proposals": [], "events": []}


def _save_json(data: Dict[str, Any]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _row_from_sql(r: Dict[str, Any]) -> Dict[str, Any]:
    args = r.get("ArgsJson") or "{}"
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    return {
        "proposal_id": str(r.get("ProposalID") or ""),
        "people_id": str(r.get("PeopleID") or "") if r.get("PeopleID") is not None else "",
        "business_id": str(r.get("BusinessID")) if r.get("BusinessID") is not None else None,
        "thread_id": r.get("ThreadID") or "",
        "tool": r.get("ToolName") or "",
        "args": args,
        "risk": r.get("RiskClass") or "low_write",
        "domain": r.get("Domain") or "general",
        "summary": r.get("Summary") or "",
        "status": r.get("Status") or "pending",
        "decided_by": str(r.get("DecidedBy")) if r.get("DecidedBy") is not None else None,
        "execution_result": r.get("ExecutionResult"),
        "created_at": str(r.get("CreatedAt") or ""),
        "updated_at": str(r.get("UpdatedAt") or ""),
    }


def _append_event_sql(proposal_id: str, event_type: str, meta: Optional[Dict[str, Any]] = None) -> None:
    if not table_exists("SaigeProposalEvents"):
        return
    sql_execute(
        """
        INSERT INTO dbo.SaigeProposalEvents (EventID, ProposalID, EventType, MetaJson)
        VALUES (%s, %s, %s, %s)
        """,
        (str(uuid.uuid4()), proposal_id, event_type, json.dumps(meta or {}, default=str)),
    )


def create_proposals(
    *,
    people_id: str,
    business_id: Optional[str],
    thread_id: str,
    drafts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    created: List[Dict[str, Any]] = []
    now = _utcnow()

    if _use_sql():
        for draft in drafts or []:
            pid = str(uuid.uuid4())
            people_i = int(people_id) if str(people_id).isdigit() else None
            biz_i = int(business_id) if business_id and str(business_id).isdigit() else None
            sql_execute(
                """
                INSERT INTO dbo.SaigeProposals
                  (ProposalID, PeopleID, BusinessID, ThreadID, ToolName, ArgsJson,
                   RiskClass, Domain, Summary, Status, CreatedAt, UpdatedAt)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',SYSUTCDATETIME(),SYSUTCDATETIME())
                """,
                (
                    pid,
                    people_i,
                    biz_i,
                    str(thread_id or ""),
                    draft.get("tool") or "unknown",
                    json.dumps(draft.get("args") or {}, default=str),
                    draft.get("risk") or "low_write",
                    draft.get("domain") or "general",
                    (draft.get("summary") or "")[:500],
                ),
            )
            _append_event_sql(pid, "proposed", {})
            created.append(
                {
                    "proposal_id": pid,
                    "people_id": str(people_id or ""),
                    "business_id": str(business_id) if business_id else None,
                    "thread_id": str(thread_id or ""),
                    "tool": draft.get("tool") or "unknown",
                    "args": draft.get("args") or {},
                    "risk": draft.get("risk") or "low_write",
                    "domain": draft.get("domain") or "general",
                    "summary": draft.get("summary") or "",
                    "status": "pending",
                    "created_at": now,
                    "updated_at": now,
                }
            )
        logger.info("[Proposals] SQL created %s pending", len(created))
        return created

    with _LOCK:
        data = _ensure_json()
        for draft in drafts or []:
            row = {
                "proposal_id": str(uuid.uuid4()),
                "people_id": str(people_id or ""),
                "business_id": str(business_id or "") if business_id else None,
                "thread_id": str(thread_id or ""),
                "tool": draft.get("tool") or "unknown",
                "args": draft.get("args") or {},
                "risk": draft.get("risk") or "low_write",
                "domain": draft.get("domain") or "general",
                "summary": draft.get("summary") or "",
                "status": "pending",
                "created_at": now,
                "updated_at": now,
            }
            data["proposals"].append(row)
            data["events"].append(
                {
                    "event_id": str(uuid.uuid4()),
                    "proposal_id": row["proposal_id"],
                    "event_type": "proposed",
                    "at": now,
                    "meta": {},
                }
            )
            created.append(row)
        _save_json(data)
    logger.info("[Proposals] JSON created %s pending", len(created))
    return created


def decide_proposal(
    proposal_id: str,
    *,
    decision: str,
    edits: Optional[Dict[str, Any]] = None,
    decided_by: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    decision = (decision or "").strip().lower()
    if decision not in {"approve", "edit", "reject"}:
        raise ValueError("decision must be approve | edit | reject")

    if _use_sql():
        row = get_proposal(proposal_id)
        if not row:
            return None
        args = dict(row.get("args") or {})
        if decision == "edit" and edits:
            args.update(edits)
            status = "approved"
            event_type = "edited_approved"
        elif decision == "approve":
            status = "approved"
            event_type = "approved"
        else:
            status = "rejected"
            event_type = "rejected"
        decided_i = int(decided_by) if decided_by and str(decided_by).isdigit() else None
        sql_execute(
            """
            UPDATE dbo.SaigeProposals
            SET Status=%s, ArgsJson=%s, DecidedBy=%s, UpdatedAt=SYSUTCDATETIME()
            WHERE ProposalID=%s
            """,
            (status, json.dumps(args, default=str), decided_i, proposal_id),
        )
        _append_event_sql(proposal_id, event_type, {"edits": edits or {}})
        return get_proposal(proposal_id)

    with _LOCK:
        data = _ensure_json()
        for row in data["proposals"]:
            if row.get("proposal_id") != proposal_id:
                continue
            now = _utcnow()
            if decision == "edit" and edits:
                args = dict(row.get("args") or {})
                args.update(edits)
                row["args"] = args
                row["status"] = "approved"
                event_type = "edited_approved"
            elif decision == "approve":
                row["status"] = "approved"
                event_type = "approved"
            else:
                row["status"] = "rejected"
                event_type = "rejected"
            row["updated_at"] = now
            row["decided_by"] = decided_by
            data["events"].append(
                {
                    "event_id": str(uuid.uuid4()),
                    "proposal_id": proposal_id,
                    "event_type": event_type,
                    "at": now,
                    "meta": {"edits": edits or {}},
                }
            )
            _save_json(data)
            return row
    return None


def mark_executed(proposal_id: str, *, ok: bool, result: str = "") -> None:
    status = "executed" if ok else "failed"
    if _use_sql():
        sql_execute(
            """
            UPDATE dbo.SaigeProposals
            SET Status=%s, ExecutionResult=%s, UpdatedAt=SYSUTCDATETIME()
            WHERE ProposalID=%s
            """,
            (status, (result or "")[:4000], proposal_id),
        )
        _append_event_sql(proposal_id, status, {"result": (result or "")[:500]})
        return

    with _LOCK:
        data = _ensure_json()
        now = _utcnow()
        for row in data["proposals"]:
            if row.get("proposal_id") == proposal_id:
                row["status"] = status
                row["updated_at"] = now
                row["execution_result"] = result
                break
        data["events"].append(
            {
                "event_id": str(uuid.uuid4()),
                "proposal_id": proposal_id,
                "event_type": status,
                "at": now,
                "meta": {"result": result[:500]},
            }
        )
        _save_json(data)


def list_proposals(
    *,
    people_id: Optional[str] = None,
    business_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    if _use_sql():
        where = ["1=1"]
        params: List[Any] = []
        if people_id and str(people_id).isdigit():
            where.append("PeopleID=%s")
            params.append(int(people_id))
        if business_id and str(business_id).isdigit():
            where.append("BusinessID=%s")
            params.append(int(business_id))
        if status:
            where.append("Status=%s")
            params.append(status)
        sql = (
            f"SELECT TOP {max(1, int(limit))} * FROM dbo.SaigeProposals "
            f"WHERE {' AND '.join(where)} ORDER BY CreatedAt DESC"
        )
        return [_row_from_sql(r) for r in sql_fetch_all(sql, tuple(params))]

    with _LOCK:
        data = _ensure_json()
        rows = list(data.get("proposals") or [])
    if people_id:
        rows = [r for r in rows if r.get("people_id") == str(people_id)]
    if business_id:
        rows = [r for r in rows if r.get("business_id") == str(business_id)]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[:limit]


def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    if _use_sql():
        r = sql_fetch_one("SELECT * FROM dbo.SaigeProposals WHERE ProposalID=%s", (proposal_id,))
        return _row_from_sql(r) if r else None
    with _LOCK:
        data = _ensure_json()
        for row in data.get("proposals") or []:
            if row.get("proposal_id") == proposal_id:
                return row
    return None


def list_proposal_events(proposal_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Audit trail for a proposal."""
    if _use_sql() and table_exists("SaigeProposalEvents"):
        rows = sql_fetch_all(
            f"SELECT TOP {max(1, int(limit))} * FROM dbo.SaigeProposalEvents WHERE ProposalID=%s ORDER BY CreatedAt DESC",
            (proposal_id,),
        )
        out = []
        for r in rows:
            meta = r.get("MetaJson") or "{}"
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            out.append(
                {
                    "event_id": str(r.get("EventID") or ""),
                    "proposal_id": proposal_id,
                    "event_type": r.get("EventType"),
                    "at": str(r.get("CreatedAt") or ""),
                    "meta": meta,
                }
            )
        return out
    with _LOCK:
        data = _ensure_json()
        ev = [e for e in (data.get("events") or []) if e.get("proposal_id") == proposal_id]
    ev.sort(key=lambda e: e.get("at") or "", reverse=True)
    return ev[:limit]
