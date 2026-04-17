"""
Google Earth Engine helper — fetch a recent cloud-free Sentinel-2 RGB thumbnail
for a field's bounding geometry and return a URL the biomass estimator can read.

Requires:
  pip install earthengine-api
  env GEE_SERVICE_ACCOUNT=svc@project.iam.gserviceaccount.com
  env GEE_KEY_FILE=/path/to/key.json  (or GOOGLE_APPLICATION_CREDENTIALS)

On any failure (not installed / not configured / no imagery) returns None.
Callers should handle None → HTTP 503 "satellite imagery unavailable".
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Optional


_initialized = False


def _ensure_initialized() -> bool:
    global _initialized
    if _initialized:
        return True
    try:
        import ee  # type: ignore
    except ImportError:
        return False

    svc_account = os.getenv("GEE_SERVICE_ACCOUNT")
    key_file = os.getenv("GEE_KEY_FILE") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    try:
        if svc_account and key_file:
            creds = ee.ServiceAccountCredentials(svc_account, key_file)
            ee.Initialize(credentials=creds)
        else:
            ee.Initialize()
        _initialized = True
        return True
    except Exception as e:
        print(f"[gee_helper] init failed: {e}")
        return False


def get_sentinel2_thumbnail_url(
    latitude: Optional[float],
    longitude: Optional[float],
    boundary_geojson: Optional[str] = None,
    days_back: int = 30,
    buffer_meters: int = 250,
) -> Optional[dict]:
    """
    Returns {"url": str, "captured_at": iso} for the most recent cloud-free
    Sentinel-2 L2A RGB composite within `days_back` days, or None if unavailable.
    """
    if not _ensure_initialized():
        return None
    try:
        import ee  # type: ignore

        if boundary_geojson:
            try:
                geom = ee.Geometry(json.loads(boundary_geojson))
            except Exception:
                geom = None
        else:
            geom = None

        if geom is None:
            if latitude is None or longitude is None:
                return None
            geom = ee.Geometry.Point([float(longitude), float(latitude)]).buffer(buffer_meters)

        end = datetime.utcnow()
        start = end - timedelta(days=days_back)

        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom)
            .filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            .sort("system:time_start", False)
        )

        size = collection.size().getInfo()
        if not size:
            return None

        image = ee.Image(collection.first())
        captured_ms = image.get("system:time_start").getInfo()
        captured_at = datetime.utcfromtimestamp(captured_ms / 1000).isoformat() + "Z"

        vis = {
            "bands": ["B4", "B3", "B2"],
            "min": 0,
            "max": 3000,
            "gamma": 1.1,
        }
        url = image.clip(geom).getThumbURL({**vis, "region": geom, "dimensions": 512, "format": "png"})
        return {"url": url, "captured_at": captured_at}
    except Exception as e:
        print(f"[gee_helper] fetch failed: {e}")
        return None
