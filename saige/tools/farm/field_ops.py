# --- tools/farm/field_ops.py ---
"""HITL-only field mutations. Called from execute_registry after approval."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from config import DB_CONFIG, OFN_BACKEND_URL

logger = logging.getLogger("farm_advisory.field_ops")

try:
    import pymssql
    _OK = True
except ImportError:
    _OK = False

try:
    import requests as _requests
except ImportError:
    _requests = None

_HTTP_TIMEOUT = 20


def _connect():
    if not _OK or not all([DB_CONFIG.get("host"), DB_CONFIG.get("user"), DB_CONFIG.get("database")]):
        return None
    try:
        return pymssql.connect(
            server=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            timeout=12,
            login_timeout=12,
        )
    except Exception as e:
        logger.error("[field_ops] connect: %s", e)
        return None


def _business_owns_field(conn, field_id: int, business_id: int) -> bool:
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT TOP 1 FieldID FROM Field WHERE FieldID=%s AND BusinessID=%s",
        (int(field_id), int(business_id)),
    )
    return bool(cur.fetchone())


def _size_hectares(
    size_hectares: Optional[float],
    size_acres: Optional[float],
) -> Optional[float]:
    if size_hectares is not None:
        try:
            return float(size_hectares)
        except Exception:
            pass
    if size_acres is not None:
        try:
            return float(size_acres) * 0.404686
        except Exception:
            pass
    return None


def _create_field_via_api(
    *,
    business_id: int,
    name: str,
    crop_type: str = "",
    size_hectares: Optional[float] = None,
    planting_date: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    address: str = "",
) -> Optional[str]:
    """Prefer dashboard create path: POST /api/fields (monitoring enabled by default)."""
    if not _requests or not OFN_BACKEND_URL:
        return None
    payload: Dict[str, Any] = {
        "business_id": int(business_id),
        "name": name,
        "monitoring_interval_days": 5,
        "alert_threshold_health": 50,
    }
    if crop_type:
        payload["crop_type"] = str(crop_type)[:100]
    if size_hectares is not None:
        payload["field_size_hectares"] = float(size_hectares)
    if planting_date:
        payload["planting_date"] = str(planting_date)[:32]
    if latitude is not None:
        payload["latitude"] = float(latitude)
    if longitude is not None:
        payload["longitude"] = float(longitude)
    if address:
        payload["address"] = str(address)[:500]
    try:
        r = _requests.post(
            f"{OFN_BACKEND_URL}/api/fields",
            json=payload,
            timeout=_HTTP_TIMEOUT,
        )
        if r.status_code >= 400:
            logger.warning(
                "[field_ops] POST /api/fields failed status=%s body=%s",
                r.status_code,
                (r.text or "")[:300],
            )
            return None
        data = r.json() if r.content else {}
        fid = data.get("id") or data.get("FieldID") or data.get("fieldid")
        created_name = data.get("name") or name
        if fid:
            return (
                f"Created field '{created_name}' (FieldID={fid}) for business #{business_id} "
                "with monitoring enabled."
            )
        return f"Created field '{created_name}' for business #{business_id} with monitoring enabled."
    except Exception as e:
        logger.warning("[field_ops] POST /api/fields error: %s", e)
        return None


def _create_field_via_sql(
    *,
    business_id: int,
    people_id: Optional[str] = None,
    name: str = "",
    crop_type: str = "",
    size_hectares: Optional[float] = None,
    planting_date: str = "",
    monitoring_enabled: bool = True,
    description: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> str:
    conn = _connect()
    if not conn:
        return "Database unavailable — could not create field."
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 FieldID FROM Field WHERE BusinessID=%s AND Name=%s",
            (int(business_id), name),
        )
        if cur.fetchone():
            return f"A field named '{name}' already exists for business #{business_id}."
        pid = int(people_id) if people_id and str(people_id).isdigit() else None
        cur.execute(
            """
            INSERT INTO Field
            (BusinessID, Name, Address, CropType, Latitude, Longitude,
             FieldSizeHectares, PlantingDate, FieldDescription,
             MonitoringEnabled, MonitoringIntervalDays, AlertThresholdHealth,
             CreatedByPeopleID, CreatedAt)
            OUTPUT INSERTED.FieldID
            VALUES (%s, %s, '', %s, %s, %s, %s, %s, %s, %s, 5, 50, %s, GETUTCDATE())
            """,
            (
                int(business_id),
                name,
                (crop_type or None) and str(crop_type)[:100],
                latitude,
                longitude,
                size_hectares,
                (planting_date or None) and str(planting_date)[:32],
                (description or None) and str(description)[:2000],
                1 if monitoring_enabled else 0,
                pid,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        fid = row[0] if row else None
        return f"Created field '{name}' (FieldID={fid}) for business #{business_id}."
    except Exception as e:
        logger.exception("[field_ops] create_field SQL")
        try:
            conn.rollback()
        except Exception:
            pass
        return f"Could not create field: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def create_field(
    *,
    business_id: int,
    people_id: Optional[str] = None,
    name: str = "",
    crop_type: str = "",
    size_hectares: Optional[float] = None,
    size_acres: Optional[float] = None,
    planting_date: str = "",
    monitoring_enabled: bool = True,
    description: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    address: str = "",
) -> str:
    try:
        bid = int(business_id or 0)
    except Exception:
        bid = 0
    if bid <= 0:
        return (
            "No business is linked to this session — select a business in your account "
            "before creating a precision-ag field."
        )
    name = (name or "New Field").strip()[:200]
    if not name:
        return "Field name is required."
    ha = _size_hectares(size_hectares, size_acres)

    via_api = _create_field_via_api(
        business_id=bid,
        name=name,
        crop_type=crop_type or "",
        size_hectares=ha,
        planting_date=planting_date or "",
        latitude=latitude,
        longitude=longitude,
        address=address or "",
    )
    if via_api:
        return via_api

    logger.info("[field_ops] falling back to SQL create_field for business #%s", bid)
    return _create_field_via_sql(
        business_id=bid,
        people_id=people_id,
        name=name,
        crop_type=crop_type or "",
        size_hectares=ha,
        planting_date=planting_date or "",
        monitoring_enabled=True if monitoring_enabled is None else bool(monitoring_enabled),
        description=description or "",
        latitude=latitude,
        longitude=longitude,
    )


def update_field(
    *,
    business_id: int,
    field_id: int,
    name: str = "",
    crop_type: str = "",
    size_hectares: Optional[float] = None,
    size_acres: Optional[float] = None,
    planting_date: str = "",
    description: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> str:
    if not business_id or not field_id:
        return "business_id and field_id are required."
    conn = _connect()
    if not conn:
        return "Database unavailable."
    try:
        if not _business_owns_field(conn, field_id, business_id):
            return f"Field #{field_id} not found for business #{business_id}."
        ha = _size_hectares(size_hectares, size_acres)
        sets = []
        params = []
        if name:
            sets.append("Name = %s")
            params.append(str(name)[:200])
        if crop_type:
            sets.append("CropType = %s")
            params.append(str(crop_type)[:100])
        if ha is not None:
            sets.append("FieldSizeHectares = %s")
            params.append(float(ha))
        if planting_date:
            sets.append("PlantingDate = %s")
            params.append(str(planting_date)[:32])
        if description:
            sets.append("FieldDescription = %s")
            params.append(str(description)[:2000])
        if latitude is not None:
            sets.append("Latitude = %s")
            params.append(float(latitude))
        if longitude is not None:
            sets.append("Longitude = %s")
            params.append(float(longitude))
        if not sets:
            return "Nothing to update on field."
        params.extend([int(field_id), int(business_id)])
        cur = conn.cursor()
        cur.execute(
            f"UPDATE Field SET {', '.join(sets)} WHERE FieldID=%s AND BusinessID=%s",
            tuple(params),
        )
        conn.commit()
        return f"Updated field #{field_id} ({len(sets)} field(s))."
    except Exception as e:
        logger.exception("[field_ops] update_field")
        try:
            conn.rollback()
        except Exception:
            pass
        return f"Could not update field: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def toggle_monitoring(
    *,
    business_id: int,
    field_id: int,
    enabled: bool = True,
    interval_days: int = 7,
) -> str:
    if not business_id or not field_id:
        return "business_id and field_id are required."
    conn = _connect()
    if not conn:
        return "Database unavailable."
    try:
        if not _business_owns_field(conn, field_id, business_id):
            return f"Field #{field_id} not found for business #{business_id}."
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE Field
            SET MonitoringEnabled=%s, MonitoringIntervalDays=%s
            WHERE FieldID=%s AND BusinessID=%s
            """,
            (1 if enabled else 0, max(1, int(interval_days or 7)), int(field_id), int(business_id)),
        )
        conn.commit()
        state = "enabled" if enabled else "disabled"
        return f"Monitoring {state} on field #{field_id}."
    except Exception as e:
        logger.exception("[field_ops] toggle_monitoring")
        try:
            conn.rollback()
        except Exception:
            pass
        return f"Could not toggle monitoring: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def parse_field_create_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize proposal args from LLM / heuristics into create_field kwargs."""
    raw = args.get("raw_request") or ""
    name = args.get("name") or args.get("field_name") or args.get("FieldName") or ""
    crop = args.get("crop_type") or args.get("crop") or args.get("CropType") or ""
    size_acres = args.get("size_acres") or args.get("acres")
    size_ha = args.get("size_hectares") or args.get("hectares") or args.get("FieldSizeHectares")
    if not name and raw:
        import re
        m = re.search(r"(?:called|named)\s+([A-Za-z0-9][\w\s-]{1,40})", raw, re.I)
        if m:
            name = m.group(1).strip()
        m2 = re.search(r"(\d+(?:\.\d+)?)\s*acres?", raw, re.I)
        if m2 and size_acres is None:
            size_acres = float(m2.group(1))
        for c in ("corn", "wheat", "soy", "alfalfa", "tomato", "potato", "hay", "barley", "oats"):
            if c in raw.lower() and not crop:
                crop = c
                break
    # Default monitoring on for new fields unless explicitly disabled
    mon_raw = args.get("monitoring_enabled", args.get("enable_monitoring", True))
    if isinstance(mon_raw, str):
        monitoring_enabled = mon_raw.strip().lower() not in {"0", "false", "no", "off"}
    else:
        monitoring_enabled = bool(mon_raw) if mon_raw is not None else True
    out: Dict[str, Any] = {
        "business_id": int(args.get("business_id") or 0),
        "people_id": str(args.get("people_id") or "") or None,
        "name": name or "New Field",
        "crop_type": crop or "",
        "monitoring_enabled": monitoring_enabled,
        "description": args.get("description") or "",
        "planting_date": args.get("planting_date") or "",
        "address": args.get("address") or "",
    }
    if size_acres is not None:
        try:
            out["size_acres"] = float(size_acres)
        except Exception:
            pass
    if size_ha is not None:
        try:
            out["size_hectares"] = float(size_ha)
        except Exception:
            pass
    if args.get("latitude") is not None:
        try:
            out["latitude"] = float(args.get("latitude"))
        except Exception:
            pass
    if args.get("longitude") is not None:
        try:
            out["longitude"] = float(args.get("longitude"))
        except Exception:
            pass
    return out
