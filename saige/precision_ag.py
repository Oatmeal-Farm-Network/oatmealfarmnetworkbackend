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



# ---------------------------------------------------------------------------
# HTTP helper — calls the OFN backend (port 8000) for computed endpoints
# ---------------------------------------------------------------------------

import requests as _requests

_BACKEND_URL = os.getenv("OFN_BACKEND_URL", "http://localhost:8000").rstrip("/")
_HTTP_TIMEOUT = 10


def _api_get(path: str) -> Optional[Dict[str, Any]]:
    try:
        r = _requests.get(f"{_BACKEND_URL}{path}", timeout=_HTTP_TIMEOUT)
        return r.json() if r.ok else None
    except Exception as e:
        print(f"[precision_ag] HTTP GET {path} failed: {e}")
        return None


def _api_post(path: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        r = _requests.post(f"{_BACKEND_URL}{path}", json=body, timeout=_HTTP_TIMEOUT)
        return r.json() if r.ok else None
    except Exception as e:
        print(f"[precision_ag] HTTP POST {path} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# SOIL SAMPLES
# ---------------------------------------------------------------------------

@tool
def get_field_soil_samples_tool(field_id: int, people_id: str = "") -> str:
    """Get soil sample data for a field — pH, organic matter, nitrogen, phosphorus,
    potassium, and other nutrients. Saige interprets optimal ranges and flags
    deficiencies or excesses so the farmer knows exactly what amendments are needed.
    Use when the user asks about soil health, nutrient levels, fertilizer recommendations,
    or "what does my soil need". people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch soil samples — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    rows = _query(
        "SELECT TOP 10 SampleLabel, SampleDate, Depth_cm, pH, OrganicMatter, "
        "Nitrogen, Phosphorus, Potassium, Sulfur, Calcium, Magnesium, CEC, Notes "
        "FROM dbo.FieldSoilSample WHERE FieldID = %s ORDER BY SampleDate DESC",
        (int(field_id),),
    )
    if not rows:
        return (f"No soil samples on record for field #{field_id} "
                f"({field.get('name') or 'Unnamed'}). "
                "Add samples in the Precision Ag → Soil Samples section.")

    # Optimal ranges for interpretation
    RANGES = {
        "ph": (6.0, 7.0, "acidic (<6)", "optimal (6–7)", "alkaline (>7)"),
        "organicmatter": (2.0, 5.0, "low OM (<2%) — add compost", "good OM (2–5%)", "high OM (>5%)"),
        "nitrogen": (20, 60, "N deficient", "adequate N", "high N"),
        "phosphorus": (15, 40, "P deficient — apply phosphate", "adequate P", "excess P — leaching risk"),
        "potassium": (100, 200, "K deficient — apply potash", "adequate K", "excess K"),
    }

    def _grade(val, key):
        if val is None:
            return "—"
        lo, hi = RANGES[key][0], RANGES[key][1]
        try:
            v = float(val)
            if v < lo:
                return f"{v:.2f} ⚠ {RANGES[key][2]}"
            if v > hi:
                return f"{v:.2f} ℹ {RANGES[key][4]}"
            return f"{v:.2f} ✓ {RANGES[key][3]}"
        except (TypeError, ValueError):
            return "—"

    lines = [f"Soil samples for field #{field_id} ({field.get('name') or 'Unnamed'}) — {len(rows)} record(s):"]
    for s in rows:
        label = s.get("samplelabel") or "Sample"
        date  = _fmt_date(s.get("sampledate"))
        depth = s.get("depth_cm") or "?"
        lines.append(f"\n  [{label} — {date}, depth {depth}cm]")
        lines.append(f"    pH: {_grade(s.get('ph'), 'ph')}")
        lines.append(f"    Organic Matter: {_grade(s.get('organicmatter'), 'organicmatter')}")
        lines.append(f"    N: {_grade(s.get('nitrogen'), 'nitrogen')} kg/ha")
        lines.append(f"    P: {_grade(s.get('phosphorus'), 'phosphorus')} kg/ha")
        lines.append(f"    K: {_grade(s.get('potassium'), 'potassium')} kg/ha")
        if s.get("cec"):
            lines.append(f"    CEC: {_fmt_num(s.get('cec'), 1)} meq/100g")
        if s.get("notes"):
            lines.append(f"    Notes: {s['notes']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SCOUTING
# ---------------------------------------------------------------------------

@tool
def get_field_scouting_tool(field_id: int, people_id: str = "") -> str:
    """Get recent field scouting observations — pest sightings, disease, weed
    pressure, nutrient deficiency symptoms, irrigation issues. Each observation
    has a category and severity (Low/Medium/High/Critical). Use when the user
    asks "what scouting issues are on my field", "any pests found", "what's been
    observed in the field", or wants to understand in-field conditions beyond
    satellite data. people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch scouting data — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    rows = _query(
        "SELECT TOP 20 ScoutID, ObservedAt, Category, Severity, Notes "
        "FROM dbo.FieldScout WHERE FieldID = %s ORDER BY ObservedAt DESC",
        (int(field_id),),
    )
    if not rows:
        return (f"No scouting observations logged for field #{field_id} "
                f"({field.get('name') or 'Unnamed'}). "
                "Add observations in Precision Ag → Scouting.")
    lines = [f"Scouting log for field #{field_id} ({field.get('name') or 'Unnamed'}) — {len(rows)} observation(s):"]
    critical_high = [r for r in rows if str(r.get("severity") or "").lower() in ("critical", "high")]
    if critical_high:
        lines.append(f"  ⚠ {len(critical_high)} High/Critical severity issue(s) require attention!")
    for r in rows:
        sev = r.get("severity") or "—"
        cat = r.get("category") or "General"
        notes = (r.get("notes") or "").strip()
        date  = _fmt_date(r.get("observedat"))
        icon  = {"critical": "🚨", "high": "⚠️", "medium": "⚡", "low": "ℹ️"}.get(sev.lower(), "•")
        line  = f"  {icon} [{sev.upper()}] {cat} — {date}"
        if notes:
            line += f": {notes[:120]}"
        lines.append(line)
    return "\n".join(lines)


@tool
def add_scout_observation_tool(
    field_id: int,
    category: str,
    severity: str,
    notes: str,
    people_id: str = "",
) -> str:
    """Log a new scouting observation for a field on behalf of the user. Use when
    the user tells you they found a pest, disease, weed issue, or any in-field
    observation and wants it recorded. Category options: General, Pest, Disease,
    Weed, Irrigation, Nutrient, Weather. Severity: Low, Medium, High, Critical.
    people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot log scouting — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    body = {
        "category": category,
        "severity": severity,
        "notes": notes,
        "people_id": int(people_id) if people_id and str(people_id).isdigit() else None,
    }
    result = _api_post(f"/api/fields/{field_id}/scouts", body)
    if result and result.get("scout_id"):
        return (f"✓ Scouting observation logged for field #{field_id} "
                f"({field.get('name') or 'Unnamed'}): [{severity.upper()}] {category} — {notes[:80]}")
    return "Failed to save the scouting observation. Please try again."


# ---------------------------------------------------------------------------
# ACTIVITY LOG
# ---------------------------------------------------------------------------

@tool
def get_field_activity_log_tool(field_id: int, people_id: str = "") -> str:
    """Get the recent field activity log — spray applications, fertilizer
    applications, tillage, irrigation events, planting, harvest, and other
    operations. Use when the user asks "what have we done on this field",
    "what was applied last week", "show me the operation history", or when
    building context for agronomic advice. people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch activity log — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    rows = _query(
        "SELECT TOP 20 ActivityDate, ActivityType, Product, Rate, RateUnit, "
        "OperatorName, Notes "
        "FROM dbo.FieldActivityLog WHERE FieldID = %s ORDER BY ActivityDate DESC",
        (int(field_id),),
    )
    if not rows:
        return (f"No activities logged yet for field #{field_id} "
                f"({field.get('name') or 'Unnamed'}). "
                "Log operations in Precision Ag → Activity Log.")
    lines = [f"Activity log for field #{field_id} ({field.get('name') or 'Unnamed'}) — {len(rows)} record(s):"]
    for r in rows:
        date  = _fmt_date(r.get("activitydate"))
        atype = r.get("activitytype") or "Activity"
        product = r.get("product") or ""
        rate    = r.get("rate")
        unit    = r.get("rateunit") or ""
        op      = r.get("operatorname") or ""
        notes   = (r.get("notes") or "").strip()
        rate_str = f" @ {_fmt_num(rate, 1)} {unit}".rstrip() if rate is not None else ""
        op_str   = f" by {op}" if op else ""
        line = f"  • {date} — {atype}: {product}{rate_str}{op_str}"
        if notes:
            line += f" ({notes[:80]})"
        lines.append(line)
    return "\n".join(lines)


@tool
def log_field_activity_tool(
    field_id: int,
    activity_type: str,
    activity_date: str,
    product: str = "",
    rate: float = None,
    rate_unit: str = "",
    operator_name: str = "",
    notes: str = "",
    people_id: str = "",
) -> str:
    """Log a new field operation / activity on behalf of the user. Use when the
    user says they did something on a field and wants it recorded: sprayed,
    fertilized, tilled, irrigated, planted, harvested, etc. activity_type must
    be one of: Spray, Fertilize, Tillage, Irrigation, Harvest, Planting, Scouting,
    Soil Sample, Other. activity_date should be YYYY-MM-DD format (default today).
    people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot log activity — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    body = {
        "activity_date": activity_date,
        "activity_type": activity_type,
        "product": product or None,
        "rate": rate,
        "rate_unit": rate_unit or None,
        "operator_name": operator_name or None,
        "notes": notes or None,
        "people_id": int(people_id) if people_id and str(people_id).isdigit() else None,
    }
    result = _api_post(f"/api/fields/{field_id}/activity-log", body)
    if result and result.get("activity_id"):
        detail = f"{activity_type}"
        if product:
            detail += f": {product}"
        if rate is not None:
            detail += f" @ {rate} {rate_unit}"
        return (f"✓ Activity logged for field #{field_id} "
                f"({field.get('name') or 'Unnamed'}) on {activity_date}: {detail}")
    return "Failed to save the activity. Please try again."


@tool
def add_soil_sample_tool(
    field_id: int,
    sample_label: str,
    ph: float = None,
    organic_matter: float = None,
    nitrogen: float = None,
    phosphorus: float = None,
    potassium: float = None,
    sample_date: str = "",
    depth_cm: int = 30,
    notes: str = "",
    people_id: str = "",
) -> str:
    """Record a new soil sample result for a field on behalf of the user. Use
    when the user gives you their soil test results and wants them stored.
    sample_label is a short name (e.g. 'North corner'), ph is the pH value,
    organic_matter is OM%, nitrogen/phosphorus/potassium are in kg/ha,
    depth_cm is sampling depth (default 30cm). people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot save soil sample — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    import datetime
    body = {
        "sample_label": sample_label,
        "sample_date": sample_date or datetime.date.today().isoformat(),
        "depth_cm": depth_cm,
        "ph": ph,
        "organic_matter": organic_matter,
        "nitrogen": nitrogen,
        "phosphorus": phosphorus,
        "potassium": potassium,
        "notes": notes or None,
    }
    result = _api_post(f"/api/fields/{field_id}/soil-samples", body)
    if result and result.get("sample_id"):
        parts = [f"pH={ph}" if ph is not None else None,
                 f"OM={organic_matter}%" if organic_matter is not None else None,
                 f"N={nitrogen}" if nitrogen is not None else None]
        summary = ", ".join(p for p in parts if p)
        return (f"✓ Soil sample '{sample_label}' saved for field #{field_id} "
                f"({field.get('name') or 'Unnamed'}): {summary or 'data recorded'}")
    return "Failed to save the soil sample. Please try again."


# ---------------------------------------------------------------------------
# GDD — Growing Degree Days
# ---------------------------------------------------------------------------

@tool
def get_field_gdd_tool(field_id: int, days: int = 180, people_id: str = "") -> str:
    """Get accumulated Growing Degree Days (GDD) for a field — the heat unit
    total that determines crop development stage. Saige interprets GDD against
    crop-specific milestones (emergence, flowering, maturity) to tell the farmer
    where their crop is in its development cycle. Use when the user asks about
    crop growth stage, development progress, when to expect flowering/harvest,
    or "how many GDD have we accumulated". people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch GDD — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    data = _api_get(f"/api/fields/{field_id}/gdd?days={max(30, min(int(days), 365))}")
    if not data:
        return (f"Could not retrieve GDD data for field #{field_id}. "
                "Ensure the field has GPS coordinates set.")
    total = data.get("total_gdd", 0)
    base  = data.get("base_temp_f", 50)
    crop  = data.get("crop_type") or "Unknown crop"
    daily = data.get("daily") or []
    avg   = total / max(len(daily), 1)
    lines = [
        f"Growing Degree Days — field #{field_id} ({field.get('name') or 'Unnamed'})",
        f"Crop: {crop} | Base temperature: {base}°F | Period: {days} days",
        f"Total accumulated GDD: {total:.0f}",
        f"Average GDD/day: {avg:.1f}",
    ]
    if daily:
        recent = daily[-7:] if len(daily) >= 7 else daily
        recent_total = sum(d.get("gdd", 0) for d in recent)
        lines.append(f"Last 7 days: {recent_total:.0f} GDD ({recent_total/7:.1f}/day avg)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# IRRIGATION SCHEDULING
# ---------------------------------------------------------------------------

@tool
def get_field_irrigation_tool(field_id: int, days: int = 30, people_id: str = "") -> str:
    """Get irrigation scheduling recommendation for a field based on actual
    ET₀ (evapotranspiration) and precipitation data from Open-Meteo weather.
    Returns whether to irrigate now, soon, or not needed — with specific water
    deficit in inches. Use when the user asks "should I irrigate", "when should I
    water my field", "what's the water deficit", or "is my crop water-stressed".
    people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch irrigation data — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    data = _api_get(f"/api/fields/{field_id}/irrigation?days={max(7, min(int(days), 60))}")
    if not data:
        return (f"Could not retrieve irrigation data for field #{field_id}. "
                "Ensure the field has GPS coordinates set.")
    rec    = data.get("recommendation") or "—"
    urgency = data.get("urgency") or "low"
    deficit = data.get("cumulative_deficit_in") or 0
    kc      = data.get("kc") or 1.0
    crop    = data.get("crop_type") or "Unknown"
    daily   = data.get("daily") or []
    urgency_prefix = {"high": "🚨", "medium": "⚠️", "low": "✅"}.get(urgency, "•")
    lines = [
        f"Irrigation schedule — field #{field_id} ({field.get('name') or 'Unnamed'})",
        f"Crop: {crop} | Crop coefficient (Kc): {kc}",
        f"{urgency_prefix} Recommendation: {rec}",
        f"Cumulative water deficit: {deficit:.2f} inches",
    ]
    if daily:
        last7 = daily[-7:]
        tp = sum(d.get("precip_in", 0) for d in last7)
        te = sum(d.get("etc_in", 0)   for d in last7)
        lines.append(f"Last 7 days: {tp:.2f}\" precip, {te:.2f}\" crop water use (ETc)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# YIELD FORECAST
# ---------------------------------------------------------------------------

@tool
def get_field_yield_forecast_tool(field_id: int, people_id: str = "") -> str:
    """Get the current NDVI-based yield forecast for a field — an estimate of
    expected harvest yield in kg/ha, compared to the crop-type baseline and
    the trend over recent satellite passes. Use when the user asks "what yield
    am I looking at", "will this be a good harvest", "how does my field compare
    to average yield", "is yield improving". people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch yield forecast — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    data = _api_get(f"/api/fields/{field_id}/yield-forecast")
    if not data:
        return f"Could not retrieve yield forecast for field #{field_id}."
    forecast = data.get("forecast_kgha")
    baseline = data.get("baseline_kgha")
    trend    = data.get("trend_pct")
    conf     = data.get("confidence") or "low"
    crop     = data.get("crop_type") or "Unknown"
    history  = data.get("history") or []
    if forecast is None:
        return (f"No yield forecast available for field #{field_id} ({field.get('name') or 'Unnamed'}). "
                "Run satellite analyses first.")
    vs_baseline = ((forecast - baseline) / baseline * 100) if baseline else None
    conf_note = {"high": "high confidence", "medium": "medium confidence", "low": "low confidence — more analyses needed"}.get(conf, conf)
    lines = [
        f"Yield forecast — field #{field_id} ({field.get('name') or 'Unnamed'})",
        f"Crop: {crop}",
        f"Forecast: {int(forecast):,} kg/ha ({conf_note})",
        f"Baseline (avg for {crop}): {int(baseline or 0):,} kg/ha",
    ]
    if vs_baseline is not None:
        dir_word = "above" if vs_baseline >= 0 else "below"
        lines.append(f"Performance vs baseline: {abs(vs_baseline):.1f}% {dir_word} average")
    if trend is not None:
        trend_word = "improving" if trend > 0 else ("declining" if trend < 0 else "stable")
        lines.append(f"NDVI trend: {trend_word} ({trend:+.1f}% since first analysis)")
    if history:
        latest_ndvi = history[0].get("ndvi")
        if latest_ndvi:
            lines.append(f"Latest NDVI: {latest_ndvi:.4f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CARBON & SUSTAINABILITY
# ---------------------------------------------------------------------------

@tool
def get_field_carbon_tool(field_id: int, people_id: str = "") -> str:
    """Get carbon and sustainability metrics for a field — soil organic matter
    (OM) trends, estimated soil organic carbon (SOC) stocks, crop rotation
    diversity, cover crop history, and a sustainability score. Use when the
    user asks about "carbon", "soil health trends", "how sustainable is my
    farm", "cover crop history", "crop rotation diversity", or wants to
    understand their regenerative ag progress. people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch carbon data — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    data = _api_get(f"/api/fields/{field_id}/carbon")
    if not data:
        return f"Could not retrieve carbon data for field #{field_id}."
    score    = data.get("sustainability_score") or 0
    cc       = data.get("cover_crop_seasons") or 0
    om_trend = data.get("om_trend_pct")
    soc      = data.get("latest_soc_MgCha")
    om_hist  = data.get("om_history") or []
    rotations = data.get("rotation_history") or []
    score_label = "Good" if score >= 75 else ("Fair" if score >= 50 else "Needs improvement")
    lines = [
        f"Carbon & sustainability — field #{field_id} ({field.get('name') or 'Unnamed'})",
        f"Sustainability score: {score}/100 ({score_label})",
    ]
    if soc is not None:
        lines.append(f"Soil organic carbon stock: {soc} Mg C/ha")
    if om_trend is not None:
        trend_dir = "increasing ↑" if om_trend > 0 else ("decreasing ↓" if om_trend < 0 else "stable →")
        lines.append(f"Organic matter trend: {om_trend:+.2f}% ({trend_dir})")
    if om_hist:
        latest_om = om_hist[-1]
        lines.append(f"Latest OM: {latest_om.get('om_pct')}% ({latest_om.get('date') or latest_om.get('label')})")
    lines.append(f"Cover crop seasons recorded: {cc}")
    if rotations:
        unique_crops = list(set(r.get("crop") for r in rotations if r.get("crop")))
        lines.append(f"Rotation history: {len(rotations)} seasons, {len(unique_crops)} different crops")
        recent = rotations[:3]
        lines.append("  Recent rotation: " + " → ".join(r.get("crop") or "?" for r in reversed(recent)))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BENCHMARK — compare all fields for the business
# ---------------------------------------------------------------------------

@tool
def get_farm_benchmark_tool(people_id: str = "") -> str:
    """Compare all fields on the farm by NDVI, health score, and trend — a
    ranking that shows which fields are performing best and which need attention.
    Use when the user asks "which of my fields is doing best", "compare my
    fields", "which field needs the most work", "show me a farm overview".
    people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot run benchmark — account not linked to any business."
    # Use first business ID for the benchmark
    biz_id = biz_ids[0]
    data = _api_get(f"/api/businesses/{biz_id}/benchmark")
    if not data:
        return "Could not retrieve benchmark data."
    fields = data.get("fields") or []
    if not fields:
        return "No fields with satellite data found for benchmarking."
    with_ndvi = [f for f in fields if f.get("ndvi") is not None]
    if not with_ndvi:
        return ("No fields have NDVI data yet. Run satellite analyses in "
                "Precision Ag → Analyses to start tracking performance.")
    avg_ndvi = sum(f["ndvi"] for f in with_ndvi) / len(with_ndvi)
    lines = [
        f"Farm benchmark — {len(fields)} field(s) across your operation",
        f"Average NDVI across all fields: {avg_ndvi:.3f}",
        "",
        "Ranking by NDVI:",
    ]
    for i, f in enumerate(fields, 1):
        ndvi    = f.get("ndvi")
        health  = f.get("health")
        trend   = f.get("trend")
        crop    = f.get("crop_type") or "—"
        medal   = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"#{i}")
        ndvi_str = f"{ndvi:.3f}" if ndvi is not None else "no data"
        health_str = f"{health}%" if health is not None else "—"
        trend_str = (f"{trend:+.4f}" if trend is not None else "—")
        vs = f" ({(ndvi - avg_ndvi):+.3f} vs avg)" if ndvi is not None else ""
        lines.append(f"  {medal} {f.get('name') or 'Unnamed'} [{crop}] — "
                     f"NDVI {ndvi_str}{vs} | Health {health_str} | Trend {trend_str}")
    if len(with_ndvi) >= 2:
        best  = with_ndvi[0]
        worst = with_ndvi[-1]
        lines.append("")
        lines.append(f"Best performer: {best.get('name') or 'Unnamed'} (NDVI {best['ndvi']:.3f})")
        lines.append(f"Needs most attention: {worst.get('name') or 'Unnamed'} (NDVI {worst['ndvi']:.3f})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# WEATHER (field-specific, for context in agronomic advice)
# ---------------------------------------------------------------------------

@tool
def get_field_weather_tool(field_id: int, days: int = 14, people_id: str = "") -> str:
    """Get recent weather data for a field — temperature (high/low), precipitation,
    and reference ET₀. Use when the user asks about recent weather, temperature
    conditions, rainfall totals, frost risk context, or when giving agronomic
    advice that depends on current conditions. people_id is injected from session state."""
    biz_ids = _business_ids_for_people(people_id)
    if not biz_ids:
        return "Cannot fetch weather — account not linked to any business."
    field = _field_accessible(int(field_id), biz_ids)
    if not field:
        return f"Field {field_id} is not accessible on your account."
    data = _api_get(f"/api/fields/{field_id}/weather?days={max(7, min(int(days), 30))}")
    if not data:
        return (f"Could not fetch weather for field #{field_id}. "
                "Ensure the field has GPS coordinates set.")
    daily = data.get("daily") or []
    if not daily:
        return "No weather data returned."
    recent = daily[-days:] if len(daily) >= days else daily
    # Compute summary
    precip_total = sum(d.get("precip", 0) or 0 for d in recent)
    tmax_vals = [d["temp_max"] for d in recent if d.get("temp_max") is not None]
    tmin_vals = [d["temp_min"] for d in recent if d.get("temp_min") is not None]
    avg_tmax = sum(tmax_vals) / len(tmax_vals) if tmax_vals else None
    avg_tmin = sum(tmin_vals) / len(tmin_vals) if tmin_vals else None
    lines = [
        f"Weather — field #{field_id} ({field.get('name') or 'Unnamed'}), last {len(recent)} days",
        f"Total precipitation: {precip_total:.2f} inches",
    ]
    if avg_tmax is not None:
        lines.append(f"Avg high: {avg_tmax:.1f}°F | Avg low: {avg_tmin:.1f}°F")
    # Last 7 days summary
    last7 = recent[-7:]
    lines.append("\nLast 7 days:")
    for d in last7:
        tmax = _fmt_num(d.get("temp_max"), 0) + "°F" if d.get("temp_max") is not None else "—"
        tmin = _fmt_num(d.get("temp_min"), 0) + "°F" if d.get("temp_min") is not None else "—"
        precip = _fmt_num(d.get("precip"), 2) + '"' if d.get("precip") is not None else "—"
        lines.append(f"  {d['date']} — High {tmax}, Low {tmin}, Precip {precip}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TOOL REGISTRY
# ---------------------------------------------------------------------------

precision_ag_tools = [
    list_my_fields_tool,
    get_field_analysis_tool,
    get_field_history_tool,
    get_field_alerts_tool,
    get_field_soil_samples_tool,
    get_field_scouting_tool,
    add_scout_observation_tool,
    get_field_activity_log_tool,
    log_field_activity_tool,
    add_soil_sample_tool,
    get_field_gdd_tool,
    get_field_irrigation_tool,
    get_field_yield_forecast_tool,
    get_field_carbon_tool,
    get_farm_benchmark_tool,
    get_field_weather_tool,
]
