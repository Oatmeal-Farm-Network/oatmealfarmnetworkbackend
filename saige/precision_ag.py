"""
Precision-ag tools for Saige.

Surfaces a farmer's field data (list of fields, latest satellite-based crop
analyses with NDVI/EVI/SAVI-type vegetation indices, and open alerts) to the
LLM so users can ask questions like:
  - "How are my fields doing?"
  - "What's the NDVI on my corn field?"
  - "Are there any active alerts on my fields?"
  - "Show me the trend on field 12."

The underlying data is populated by CropMonitoringBackend (a separate FastAPI
service that runs Sentinel/Landsat analyses and writes to dbo.Field,
dbo.Analysis, dbo.VegetationIndex, dbo.Alert). Saige reads those tables
directly over the shared SQL Server connection — it is never writing to them.

Access control: every query is scoped to the BusinessIDs returned by
dbo.BusinessAccess for the current PeopleID. Field access that the LLM
requests by FieldID is verified against that set before any data is returned,
so a user cannot ask about a field belonging to another business.
"""
from __future__ import annotations

import os
from typing import List, Optional, Dict, Any
from langchain_core.tools import tool

from config import DB_CONFIG, RAG_AVAILABLE

try:
    import pymssql
    _PMS_AVAILABLE = True
except ImportError:
    _PMS_AVAILABLE = False


# ---------------------------------------------------------------------------
# DB helpers (scoped to precision-ag tables; separate from saige.database
# which whitelists only livestock tables).
# ---------------------------------------------------------------------------

def _connect():
    if not _PMS_AVAILABLE or not all([DB_CONFIG.get("host"), DB_CONFIG.get("user"), DB_CONFIG.get("database")]):
        return None
    try:
        return pymssql.connect(
            server=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            as_dict=True,
        )
    except Exception as e:
        print(f"[precision_ag] DB connect failed: {e}")
        return None


def _query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = _connect()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall() or []
        return rows
    except Exception as e:
        print(f"[precision_ag] query error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _business_ids_for_people(people_id: Optional[str]) -> List[int]:
    if not people_id:
        return []
    rows = _query(
        "SELECT BusinessID FROM dbo.BusinessAccess WHERE PeopleID = %s AND (Active IS NULL OR Active = 1)",
        (str(people_id),),
    )
    return [int(r["businessid"]) for r in rows if r.get("businessid") is not None]


def _field_accessible(field_id: int, business_ids: List[int]) -> Optional[Dict[str, Any]]:
    if not field_id or not business_ids:
        return None
    placeholders = ",".join(["%s"] * len(business_ids))
    rows = _query(
        f"SELECT * FROM dbo.Field WHERE FieldID = %s AND BusinessID IN ({placeholders}) "
        f"AND (DeletedAt IS NULL)",
        (int(field_id), *business_ids),
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_date(val) -> str:
    if not val:
        return "—"
    s = str(val)
    return s.split(" ")[0].split("T")[0]


def _fmt_num(v, digits: int = 2) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _describe_ndvi(mean: Optional[float]) -> str:
    try:
        v = float(mean)
    except (TypeError, ValueError):
        return ""
    if v >= 0.7:
        return "very healthy / dense canopy"
    if v >= 0.5:
        return "healthy"
    if v >= 0.3:
        return "moderate / stressed"
    if v >= 0.1:
        return "sparse / poor canopy"
    return "bare soil or no vegetation"


# ---------------------------------------------------------------------------
# TOOLS — these expect people_id to be injected by the node from graph state.
# The LLM should NOT try to guess people_id; nodes.py overrides it.
# ---------------------------------------------------------------------------

@tool
def list_my_fields_tool(people_id: str = "") -> str:
    """List every field/plot monitored for the current user in the precision-ag
    system (CropMonitoringBackend). Returns field ID, name, crop type, size
    (hectares), planting date, and whether satellite monitoring is on. Use
    when the user asks "what fields do I have", "show my farm plots", "list
    my crops", or any question that needs the ID of one of their fields.
    Do not pass people_id — it is injected automatically from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "No fields found — your account is not linked to any business with monitored fields."
    placeholders = ",".join(["%s"] * len(biz_ids))
    rows = _query(
        f"SELECT FieldID, Name, CropType, FieldSizeHectares, PlantingDate, "
        f"MonitoringEnabled, Address FROM dbo.Field "
        f"WHERE BusinessID IN ({placeholders}) AND DeletedAt IS NULL "
        f"ORDER BY Name",
        tuple(biz_ids),
    )
    if not rows:
        return "You have no fields set up in the precision-ag system yet. Add one in the Crop Monitor dashboard to start tracking it."
    lines = [f"Fields ({len(rows)}):"]
    for f in rows:
        size = _fmt_num(f.get("fieldsizehectares"), 2)
        planted = _fmt_date(f.get("plantingdate"))
        mon = "monitored" if f.get("monitoringenabled") else "monitoring off"
        crop = f.get("croptype") or "—"
        addr = (f.get("address") or "").strip()
        parts = [f"#{f['fieldid']} {f.get('name') or 'Unnamed'}", f"crop: {crop}",
                 f"size: {size} ha", f"planted: {planted}", mon]
        if addr:
            parts.append(addr)
        lines.append("  • " + " · ".join(parts))
    return "\n".join(lines)


@tool
def get_field_analysis_tool(field_id: int, people_id: str = "") -> str:
    """Get the latest satellite crop analysis for a specific field — vegetation
    indices (NDVI, EVI, SAVI, etc.), analysis date, cloud percent. Also shows
    the trend vs. the previous analysis so the farmer knows if the field is
    improving or declining. Use when the user asks "how is field X doing",
    "what's the NDVI on my corn field", "is my field healthy", or wants to
    judge current crop condition. people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot look up field analysis — your account is not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} does not exist or is not accessible on your account."
    analyses = _query(
        "SELECT TOP 2 AnalysisID, AnalysisDate, CloudPercent, SatelliteAcquiredAt "
        "FROM dbo.Analysis WHERE FieldID = %s ORDER BY AnalysisDate DESC",
        (int(field_id),),
    )
    if not analyses:
        return (f"Field #{field_id} ({field.get('name') or 'Unnamed'}) has no satellite "
                "analyses yet. Trigger one from the Crop Monitor dashboard or wait for "
                "the next scheduled run.")
    latest = analyses[0]
    prev = analyses[1] if len(analyses) > 1 else None
    latest_idx = _query(
        "SELECT IndexType, MeanValue, MinValue, MaxValue, StdDev "
        "FROM dbo.VegetationIndex WHERE AnalysisID = %s",
        (latest["analysisid"],),
    )
    prev_idx_map: Dict[str, float] = {}
    if prev:
        prev_rows = _query(
            "SELECT IndexType, MeanValue FROM dbo.VegetationIndex WHERE AnalysisID = %s",
            (prev["analysisid"],),
        )
        for r in prev_rows:
            try:
                prev_idx_map[str(r["indextype"]).lower()] = float(r["meanvalue"])
            except (TypeError, ValueError):
                continue

    lines = [
        f"Field #{field_id} — {field.get('name') or 'Unnamed'} ({field.get('croptype') or 'crop n/a'})",
        f"Latest analysis: {_fmt_date(latest.get('analysisdate'))} "
        f"(cloud cover {_fmt_num(latest.get('cloudpercent'), 1)}%)",
    ]
    if not latest_idx:
        lines.append("No vegetation indices recorded for this analysis.")
    else:
        for idx in latest_idx:
            itype = str(idx.get("indextype") or "").upper()
            mean = idx.get("meanvalue")
            try:
                mean_f = float(mean) if mean is not None else None
            except (TypeError, ValueError):
                mean_f = None
            prev_val = prev_idx_map.get(str(idx.get("indextype") or "").lower())
            trend = ""
            if mean_f is not None and prev_val is not None:
                delta = mean_f - prev_val
                arrow = "↑" if delta > 0.02 else ("↓" if delta < -0.02 else "→")
                trend = f"  ({arrow} {delta:+.3f} vs {_fmt_date(prev['analysisdate'])})"
            descriptor = f" — {_describe_ndvi(mean_f)}" if itype == "NDVI" and mean_f is not None else ""
            lines.append(
                f"  • {itype}: mean {_fmt_num(mean_f, 3)} "
                f"(range {_fmt_num(idx.get('minvalue'), 3)}–{_fmt_num(idx.get('maxvalue'), 3)}){descriptor}{trend}"
            )
    return "\n".join(lines)


@tool
def get_field_history_tool(field_id: int, months: int = 6, people_id: str = "") -> str:
    """Get the NDVI / vegetation-index time series for a field over the last N
    months (default 6). Use when the user asks "show trend", "how has field X
    changed", "is my crop getting better or worse over time", or anything that
    needs history rather than a single snapshot. people_id is injected from
    session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot look up field history — your account is not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} does not exist or is not accessible on your account."
    months = max(1, min(int(months or 6), 24))
    rows = _query(
        "SELECT a.AnalysisID, a.AnalysisDate, a.CloudPercent, "
        "       v.IndexType, v.MeanValue "
        "FROM dbo.Analysis a "
        "LEFT JOIN dbo.VegetationIndex v ON v.AnalysisID = a.AnalysisID "
        "WHERE a.FieldID = %s "
        f"  AND a.AnalysisDate >= DATEADD(month, -{months}, GETDATE()) "
        "ORDER BY a.AnalysisDate DESC",
        (int(field_id),),
    )
    if not rows:
        return (f"No analyses in the last {months} months for field #{field_id} "
                f"({field.get('name') or 'Unnamed'}).")
    # Group by AnalysisDate → index map
    by_date: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        d = _fmt_date(r.get("analysisdate"))
        slot = by_date.setdefault(d, {"cloud": r.get("cloudpercent"), "idx": {}})
        it = str(r.get("indextype") or "").upper()
        if it:
            slot["idx"][it] = r.get("meanvalue")
    lines = [
        f"Field #{field_id} — {field.get('name') or 'Unnamed'} ({field.get('croptype') or 'crop n/a'})",
        f"Last {months} months ({len(by_date)} analyses):",
    ]
    ndvi_trend: List[str] = []
    for date, info in sorted(by_date.items(), reverse=True)[:15]:
        parts = [date]
        for key in ["NDVI", "EVI", "SAVI", "NDMI", "NDWI"]:
            if key in info["idx"] and info["idx"][key] is not None:
                parts.append(f"{key}={_fmt_num(info['idx'][key], 3)}")
        if info.get("cloud") is not None:
            parts.append(f"cloud={_fmt_num(info['cloud'], 0)}%")
        lines.append("  • " + " · ".join(parts))
        if "NDVI" in info["idx"] and info["idx"]["NDVI"] is not None:
            ndvi_trend.append(_fmt_num(info["idx"]["NDVI"], 3))
    if len(ndvi_trend) >= 2:
        try:
            first = float(ndvi_trend[-1])
            last = float(ndvi_trend[0])
            delta = last - first
            direction = "rising" if delta > 0.05 else ("falling" if delta < -0.05 else "steady")
            lines.append(f"NDVI trend over window: {direction} ({first:.3f} → {last:.3f}, Δ {delta:+.3f})")
        except ValueError:
            pass
    return "\n".join(lines)


@tool
def get_field_alerts_tool(field_id: int = 0, people_id: str = "") -> str:
    """List active/open precision-ag alerts (low NDVI, stress events, dropped
    monitoring coverage, etc.). Pass field_id=0 to see all open alerts across
    every field on the account; pass a specific field_id to narrow to one
    field. Use when the user asks "any alerts", "anything wrong with my
    fields", "what needs my attention". people_id is injected from session
    state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch alerts — your account is not linked to any business."
    placeholders = ",".join(["%s"] * len(biz_ids))
    if field_id and int(field_id) > 0:
        field = _field_accessible(int(field_id), biz_ids)
        if not field:
            return f"Field {field_id} does not exist or is not accessible on your account."
        rows = _query(
            "SELECT TOP 20 a.AlertID, a.AlertType, a.Severity, a.Message, a.Status, "
            "       a.CreatedAt, f.Name as FieldName, a.FieldID "
            "FROM dbo.Alert a LEFT JOIN dbo.Field f ON f.FieldID = a.FieldID "
            "WHERE a.FieldID = %s AND (a.Status IS NULL OR a.Status <> 'resolved') "
            "ORDER BY a.CreatedAt DESC",
            (int(field_id),),
        )
        scope = f"field #{field_id} ({field.get('name') or 'Unnamed'})"
    else:
        rows = _query(
            "SELECT TOP 20 a.AlertID, a.AlertType, a.Severity, a.Message, a.Status, "
            "       a.CreatedAt, f.Name as FieldName, a.FieldID "
            "FROM dbo.Alert a LEFT JOIN dbo.Field f ON f.FieldID = a.FieldID "
            f"WHERE a.BusinessID IN ({placeholders}) "
            "  AND (a.Status IS NULL OR a.Status <> 'resolved') "
            "ORDER BY a.CreatedAt DESC",
            tuple(biz_ids),
        )
        scope = "all your fields"
    if not rows:
        return f"No active alerts on {scope}. All clear."
    lines = [f"Active alerts on {scope} ({len(rows)}):"]
    for a in rows:
        sev = (a.get("severity") or "").upper() or "?"
        atype = a.get("alerttype") or "alert"
        msg = (a.get("message") or "").strip()
        short_msg = msg if len(msg) <= 140 else msg[:140].rstrip() + "…"
        lines.append(
            f"  • [{sev}] field #{a.get('fieldid')} ({a.get('fieldname') or 'Unnamed'}) · "
            f"{atype} · {_fmt_date(a.get('createdat'))}"
            + (f" — {short_msg}" if short_msg else "")
        )
    return "\n".join(lines)


precision_ag_tools = [
    list_my_fields_tool,
    get_field_analysis_tool,
    get_field_history_tool,
    get_field_alerts_tool,
]
