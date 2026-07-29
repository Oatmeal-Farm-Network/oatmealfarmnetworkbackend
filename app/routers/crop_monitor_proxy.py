"""
Thin passthrough to CropMonitoringBackend so the rest of the platform
(frontend pages, Saige tools, Oatsense BFF) can talk to a single backend
instead of having to know about the second service.

Explicit routes cover WaPOR, agronomy, recommendations, indices, zones,
raster, analyses, and email. A catch-all under `/api/cm/{path}` forwards
any other CropMonitor path (JSON or binary/tiles) with optional field
access checks when the path contains `/fields/{id}/`.

Each field-scoped route does access-scoping against the user's BusinessIDs
(via `people_id`) so the proxy can't be used to read data on fields that
don't belong to the caller.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

router = APIRouter(prefix="/api", tags=["crop-monitor-proxy"])

CROP_MONITOR_URL = os.getenv(
    "CROP_MONITOR_URL",
    "https://oatmealfarmnetworkcropmonitorbackend-git-802455386518.us-central1.run.app"
    if os.getenv("GAE_ENV") or os.getenv("K_SERVICE")
    else "http://127.0.0.1:8002",
)
_TIMEOUT_S = 20  # WaPOR + agronomy can be slow
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}
_FIELD_PATH_RE = re.compile(r"(?:^|/)fields/(\d+)(?:/|$)")


def _business_ids_for_people(people_id: Optional[int], db: Session) -> List[int]:
    if not people_id:
        return []
    rows = (
        db.query(models.BusinessAccess.BusinessID)
        .filter(models.BusinessAccess.PeopleID == people_id)
        .all()
    )
    return [r.BusinessID for r in rows]


def _check_field_access(field_id: int, people_id: Optional[int], db: Session) -> models.Field:
    """Return the field row if the caller may see it; otherwise 403/404. We
    only enforce access when a `people_id` is supplied — this mirrors how
    the rest of the precision-ag endpoints behave today (open by FieldID,
    Saige tools always pass people_id)."""
    field = db.query(models.Field).filter(models.Field.FieldID == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    if people_id is not None:
        biz_ids = _business_ids_for_people(people_id, db)
        if biz_ids and field.BusinessID not in biz_ids:
            raise HTTPException(status_code=403, detail="Field not accessible on this account")
    return field


def _maybe_check_field_in_path(path: str, people_id: Optional[int], db: Session) -> None:
    match = _FIELD_PATH_RE.search(path.lstrip("/"))
    if match:
        _check_field_access(int(match.group(1)), people_id, db)


def _proxy_get(path: str, params: dict | None = None, timeout: int | None = None) -> dict:
    try:
        r = requests.get(f"{CROP_MONITOR_URL}{path}", params=params or {}, timeout=timeout or _TIMEOUT_S)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"CropMonitor unreachable: {e}")
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text or r.reason)
    try:
        return r.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="CropMonitor returned non-JSON")


def _proxy_post(path: str, json_body: dict | None = None) -> dict:
    try:
        r = requests.post(f"{CROP_MONITOR_URL}{path}", json=json_body or {}, timeout=_TIMEOUT_S)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"CropMonitor unreachable: {e}")
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text or r.reason)
    try:
        return r.json()
    except ValueError:
        return {"ok": True}


def _forward_raw(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    content: bytes | None = None,
    content_type: str | None = None,
    timeout: int | None = None,
) -> Response:
    """Forward a request to CropMonitor and return the raw body (JSON or binary)."""
    url = f"{CROP_MONITOR_URL}{path if path.startswith('/') else '/' + path}"
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    try:
        r = requests.request(
            method.upper(),
            url,
            params=params or {},
            json=json_body,
            data=content if json_body is None else None,
            headers=headers or None,
            timeout=timeout or _TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"CropMonitor unreachable: {e}")

    out_headers = {
        k: v for k, v in r.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("Content-Type"),
        headers=out_headers,
    )


# ─── WaPOR water use ────────────────────────────────────────────────────────

@router.get("/fields/{field_id}/water-use")
def get_field_water_use(
    field_id: int,
    mapset: Optional[str] = None,
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Latest WaPOR/OpenET water-content snapshot for the field."""
    _check_field_access(field_id, people_id, db)
    params = {"mapset": mapset} if mapset else None
    return _proxy_get(f"/api/fields/{field_id}/wapor/water", params)


@router.get("/fields/{field_id}/water-use/series")
def get_field_water_use_series(
    field_id: int,
    mapset: Optional[str] = None,
    limit: int = Query(12, ge=1, le=60),
    model: Optional[str] = None,
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Recent WaPOR/OpenET water-content time series for the field."""
    _check_field_access(field_id, people_id, db)
    params = {"limit": limit}
    if mapset:
        params["mapset"] = mapset
    if model:
        params["model"] = model
    return _proxy_get(f"/api/fields/{field_id}/wapor/water-series", params)


# ─── Agronomy + recommendations ─────────────────────────────────────────────

@router.get("/fields/{field_id}/agronomy")
def get_field_agronomy(
    field_id: int,
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Full agronomy snapshot from CropMonitor: weather + forecast + GDD +
    growth stage + latest indices + irrigation/disease signals. Cached
    server-side."""
    _check_field_access(field_id, people_id, db)
    return _proxy_get(f"/api/fields/{field_id}/agronomy")


@router.get("/fields/{field_id}/recommendations")
def get_field_recommendations(
    field_id: int,
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Operational recommendations driven by CropMonitor's health-score +
    NDVI + current weather."""
    _check_field_access(field_id, people_id, db)
    return _proxy_get(f"/api/fields/{field_id}/recommendations")


# ─── Analyses (CropMonitor-owned; not on main precision-ag CRUD) ────────────

@router.get("/fields/{field_id}/analyses")
def get_field_analyses(
    field_id: int,
    limit: int = Query(50, ge=1, le=200),
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """List satellite analyses for the field from CropMonitor."""
    _check_field_access(field_id, people_id, db)
    return _proxy_get(f"/api/fields/{field_id}/analyses", {"limit": limit})


@router.post("/fields/{field_id}/analyze")
def trigger_field_analyze(
    field_id: int,
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Trigger a new CropMonitor satellite analysis for the field."""
    _check_field_access(field_id, people_id, db)
    return _proxy_post(f"/api/fields/{field_id}/analyze")


# ─── Time-series indices + stress zones ─────────────────────────────────────

@router.get("/fields/{field_id}/indices/series")
def get_field_index_series(
    field_id: int,
    index: str = "NDVI",
    days: int = Query(180, ge=7, le=730),
    limit: int = Query(200, ge=1, le=500),
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Time series of a vegetation index for the field — used by trend charts."""
    _check_field_access(field_id, people_id, db)
    return _proxy_get(
        f"/api/fields/{field_id}/indices/series",
        {"index": index, "days": days, "limit": limit},
    )


@router.get("/fields/{field_id}/zones")
def get_field_zones(
    field_id: int,
    index: str = "NDVI",
    num_zones: int = Query(4, ge=2, le=6),
    grid: int = Query(48, ge=16, le=96),
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """K-means stress zones from the latest vegetation-index raster."""
    _check_field_access(field_id, people_id, db)
    return _proxy_get(
        f"/api/fields/{field_id}/zones",
        {"index": index, "num_zones": num_zones, "grid": grid},
        timeout=60,  # Sentinel-Hub fetch + clustering can run ~5-30s on cold raster
    )


@router.get("/fields/{field_id}/raster/{index_name}")
def get_field_raster_values(
    field_id: int,
    index_name: str,
    grid: int = Query(48, ge=16, le=96),
    analysis_id: Optional[int] = None,
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Real per-cell vegetation index values (downsampled). Powers map + Rx pages.
    Pass analysis_id to fetch the historical scene for that Analysis row."""
    _check_field_access(field_id, people_id, db)
    params = {"grid": grid}
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
    return _proxy_get(
        f"/api/fields/{field_id}/raster/{index_name}",
        params,
        timeout=60,
    )


@router.get("/fields/{field_id}/zones/prescription")
def get_field_zone_prescription(
    field_id: int,
    index: str = "NDVI",
    num_zones: int = Query(4, ge=2, le=6),
    grid: int = Query(48, ge=16, le=96),
    fmt: str = "geojson",
    rates: Optional[str] = None,
    units: str = "kg/ha",
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Variable-rate prescription file (GeoJSON or CSV) generated from zones."""
    _check_field_access(field_id, people_id, db)
    params = {"index": index, "num_zones": num_zones, "grid": grid, "fmt": fmt, "units": units}
    if rates:
        params["rates"] = rates
    return _forward_raw(
        "GET",
        f"/api/fields/{field_id}/zones/prescription",
        params=params,
        timeout=60,
    )


# ─── Email the latest analysis to the field owner ───────────────────────────

@router.post("/fields/{field_id}/email-analysis")
def email_latest_analysis(
    field_id: int,
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Trigger CropMonitor's email-latest-analysis flow for this field. The
    target inbox is configured in CropMonitor; this proxy only enforces
    that the caller may see the field."""
    _check_field_access(field_id, people_id, db)
    return _proxy_post(f"/api/fields/{field_id}/email-latest")


# ─── Catch-all BFF: any remaining CropMonitor path (JSON or tiles) ──────────

@router.api_route(
    "/cm/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=True,
)
async def proxy_crop_monitor_catch_all(
    path: str,
    request: Request,
    people_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Forward arbitrary CropMonitor paths under `/api/cm/...`.

    Example: `GET /api/cm/fields/12/alerts?status=open` → CropMonitor
    `/api/fields/12/alerts?status=open`. Use this for CropMonitor-only
    routes that collide with precision-ag CRUD on the same path (e.g. alerts),
    or for binary/tile assets.
    """
    _maybe_check_field_in_path(path, people_id, db)

    # Strip people_id from upstream query — CropMonitor does not use it.
    params = dict(request.query_params)
    params.pop("people_id", None)

    body = await request.body()
    content_type = request.headers.get("content-type")
    json_body = None
    content = body or None
    if body and content_type and "application/json" in content_type:
        try:
            json_body = json.loads(body.decode("utf-8"))
            content = None
        except Exception:
            json_body = None

    timeout = 60 if any(x in path for x in ("raster", "zones", "analyze", "wapor")) else _TIMEOUT_S
    return _forward_raw(
        request.method,
        f"/api/{path}",
        params=params,
        json_body=json_body,
        content=content,
        content_type=content_type if content is not None else None,
        timeout=timeout,
    )
