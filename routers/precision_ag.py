from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from database import get_db
from datetime import date, datetime
import json
import os
import uuid
import models
import requests
from pydantic import BaseModel, validator
from typing import Optional

router = APIRouter(prefix="/api", tags=["precision-ag"])

BIOMASS_ESTIMATOR_URL = os.getenv(
    "BIOMASS_ESTIMATOR_URL",
    "https://biomass-estimator-802455386518.us-central1.run.app",
)
BIOMASS_GCS_BUCKET = os.getenv("BIOMASS_GCS_BUCKET", "oatmeal-farm-network-images")
BIOMASS_GCS_PREFIX = os.getenv("BIOMASS_GCS_PREFIX", "biomass-uploads")


class FieldCreate(BaseModel):
    business_id: int
    name: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    field_size_hectares: Optional[float] = None
    crop_type: Optional[str] = None
    planting_date: Optional[str] = None
    boundary_geojson: Optional[str] = None
    monitoring_interval_days: Optional[int] = 5
    alert_threshold_health: Optional[int] = 50

    @validator('latitude', 'longitude', 'field_size_hectares', pre=True)
    def empty_str_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v

    @validator('planting_date', pre=True)
    def empty_date_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v


@router.get("/fields")
def get_fields(business_id: int, db: Session = Depends(get_db)):
    try:
        # Join each field to its latest row in dbo.Analysis via OUTER APPLY so
        # the dashboard can show the most recent health score without an
        # N+1 fetch per field.
        rows = db.execute(text("""
            SELECT
                F.FieldID, F.BusinessID, F.Name, F.Address,
                F.Latitude, F.Longitude, F.FieldSizeHectares,
                F.CropType, F.PlantingDate,
                F.MonitoringEnabled, F.MonitoringIntervalDays, F.AlertThresholdHealth,
                LA.AnalysisDate  AS LatestAnalysisDate,
                LA.HealthScore   AS LatestHealthScore,
                LA.Status        AS LatestStatus
            FROM Field F
            OUTER APPLY (
                SELECT TOP 1 A.AnalysisDate, A.HealthScore, A.Status
                FROM Analysis A
                WHERE A.FieldID = F.FieldID
                ORDER BY A.AnalysisDate DESC
            ) LA
            WHERE F.BusinessID = :bid AND F.DeletedAt IS NULL
            ORDER BY F.Name
        """), {"bid": business_id}).fetchall()

        return [
            {
                "fieldid":                  r.FieldID,
                "id":                       r.FieldID,
                "business_id":              r.BusinessID,
                "name":                     r.Name,
                "address":                  r.Address,
                "latitude":                 float(r.Latitude) if r.Latitude is not None else None,
                "longitude":                float(r.Longitude) if r.Longitude is not None else None,
                "field_size_hectares":      float(r.FieldSizeHectares) if r.FieldSizeHectares is not None else None,
                "crop_type":                r.CropType,
                "planting_date":            str(r.PlantingDate) if r.PlantingDate else None,
                "monitoring_enabled":       bool(r.MonitoringEnabled) if r.MonitoringEnabled is not None else True,
                "monitoring_interval_days": r.MonitoringIntervalDays,
                "alert_threshold_health":   r.AlertThresholdHealth,
                "latest_analysis_date":     r.LatestAnalysisDate.isoformat() if r.LatestAnalysisDate else None,
                "latest_health_score":      int(r.LatestHealthScore) if r.LatestHealthScore is not None else None,
                "latest_status":            r.LatestStatus,
            }
            for r in rows
        ]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fields")
def create_field(field: FieldCreate, db: Session = Depends(get_db)):
    try:
        planting_date = None
        if field.planting_date:
            try:
                planting_date = date.fromisoformat(field.planting_date)
            except ValueError:
                planting_date = None

        new_field = models.Field(
            BusinessID=             field.business_id,
            Name=                   field.name,
            Address=                field.address,
            CropType=               field.crop_type,
            Latitude=               field.latitude,
            Longitude=              field.longitude,
            FieldSizeHectares=      field.field_size_hectares,
            PlantingDate=           planting_date,
            BoundaryGeoJSON=        field.boundary_geojson,
            MonitoringIntervalDays= field.monitoring_interval_days,
            AlertThresholdHealth=   field.alert_threshold_health,
            MonitoringEnabled=      1,
            CreatedAt=              datetime.utcnow(),
        )
        db.add(new_field)
        db.commit()
        db.refresh(new_field)
        return {"id": new_field.FieldID, "name": new_field.Name}
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/fields/{field_id}")
def update_field(field_id: int, field: FieldCreate, db: Session = Depends(get_db)):
    try:
        existing = db.query(models.Field).filter(models.Field.FieldID == field_id).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Field not found")
        planting_date = None
        if field.planting_date:
            try:
                planting_date = date.fromisoformat(field.planting_date)
            except ValueError:
                planting_date = None
        existing.Name                   = field.name
        existing.Address                = field.address
        existing.CropType               = field.crop_type
        existing.Latitude               = field.latitude
        existing.Longitude              = field.longitude
        existing.FieldSizeHectares      = field.field_size_hectares
        existing.PlantingDate           = planting_date
        existing.BoundaryGeoJSON        = field.boundary_geojson
        existing.MonitoringIntervalDays = field.monitoring_interval_days
        existing.AlertThresholdHealth   = field.alert_threshold_health
        db.commit()
        db.refresh(existing)
        return {"id": existing.FieldID, "name": existing.Name}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/fields/{field_id}")
def delete_field(field_id: int, db: Session = Depends(get_db)):
    try:
        field = db.query(models.Field).filter(models.Field.FieldID == field_id).first()
        if not field:
            raise HTTPException(status_code=404, detail="Field not found")
        db.delete(field)
        db.commit()
        return {"success": True, "deleted_id": field_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/summary")
def get_dashboard_summary(business_id: int, db: Session = Depends(get_db)):
    try:
        field_count = (
            db.query(func.count(models.Field.FieldID))
            .filter(models.Field.BusinessID == business_id)
            .scalar() or 0
        )
        return {
            "field_count":    field_count,
            "analysis_count": 0,
            "open_alerts":    0,
            "average_health": None,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ── BIOMASS ANALYSIS ─────────────────────────────────────────────

def _serialize_biomass_row(row: "models.FieldBiomassAnalysis") -> dict:
    return {
        "analysis_id":        row.AnalysisID,
        "field_id":           row.FieldID,
        "source":             row.Source,
        "biomass_kg_per_ha":  float(row.BiomassKgHa) if row.BiomassKgHa is not None else None,
        "confidence":         float(row.Confidence) if row.Confidence is not None else None,
        "image_url":          row.ImageUrl,
        "captured_at":        row.CapturedAt.isoformat() + "Z" if row.CapturedAt else None,
        "model_version":      row.ModelVersion,
        "features":           json.loads(row.FeaturesJSON) if row.FeaturesJSON else None,
        "created_at":         row.CreatedAt.isoformat() + "Z" if row.CreatedAt else None,
    }


def _call_estimator_url(image_url: str, source: str, field_id: int) -> dict:
    try:
        r = requests.post(
            f"{BIOMASS_ESTIMATOR_URL}/predict/url",
            json={"image_url": image_url, "source": source, "field_id": field_id},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Biomass estimator unreachable: {e}")


def _call_estimator_upload(image_bytes: bytes, filename: str, content_type: str, source: str, field_id: int) -> dict:
    try:
        r = requests.post(
            f"{BIOMASS_ESTIMATOR_URL}/predict/upload",
            files={"file": (filename, image_bytes, content_type)},
            data={"source": source, "field_id": str(field_id)},
            timeout=90,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Biomass estimator unreachable: {e}")


@router.get("/fields/{field_id}/biomass")
def get_biomass(field_id: int, db: Session = Depends(get_db)):
    """Latest satellite + latest upload analysis for a field. Returns empty
    payload (not 500) when the FieldBiomassAnalysis table hasn't been migrated yet."""
    field = db.query(models.Field).filter(models.Field.FieldID == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    empty = {"field_id": field_id, "satellite": None, "upload": None, "history": []}
    try:
        def latest(source: str):
            row = (
                db.query(models.FieldBiomassAnalysis)
                .filter(
                    models.FieldBiomassAnalysis.FieldID == field_id,
                    models.FieldBiomassAnalysis.Source == source,
                )
                .order_by(desc(models.FieldBiomassAnalysis.CapturedAt))
                .first()
            )
            return _serialize_biomass_row(row) if row else None

        history = (
            db.query(models.FieldBiomassAnalysis)
            .filter(models.FieldBiomassAnalysis.FieldID == field_id)
            .order_by(desc(models.FieldBiomassAnalysis.CreatedAt))
            .limit(20)
            .all()
        )
        return {
            "field_id":  field_id,
            "satellite": latest("satellite"),
            "upload":    latest("upload"),
            "history":   [_serialize_biomass_row(r) for r in history],
        }
    except Exception as e:
        # Most common cause: FieldBiomassAnalysis table hasn't been created yet.
        # Log and return empty so the UI shows "no analysis yet" instead of an error.
        print(f"[biomass] GET failed, returning empty (table missing?): {e}")
        db.rollback()
        return empty


@router.post("/fields/{field_id}/biomass/satellite")
def analyze_satellite(field_id: int, db: Session = Depends(get_db)):
    """Fetch recent Sentinel-2 imagery via GEE and run biomass estimator."""
    import sys
    print(f"\n===== [biomass/satellite] field_id={field_id} =====", flush=True)
    sys.stdout.flush()

    field = db.query(models.Field).filter(models.Field.FieldID == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    print(f"[biomass/satellite] field lat={field.Latitude} lon={field.Longitude} has_boundary={bool(field.BoundaryGeoJSON)}", flush=True)

    try:
        from gee_helper import get_sentinel2_thumbnail_url, is_available, last_init_error
        print("[biomass/satellite] gee_helper imported OK", flush=True)
    except ImportError as e:
        print(f"[biomass/satellite] gee_helper IMPORT FAILED: {e}", flush=True)
        raise HTTPException(status_code=503, detail=f"GEE helper unavailable: {e}")

    if not is_available():
        err = last_init_error() or "unknown reason"
        print(f"[biomass/satellite] GEE not initialized: {err}", flush=True)
        raise HTTPException(
            status_code=503,
            detail=f"Satellite imagery service is not configured: {err}",
        )

    sat = get_sentinel2_thumbnail_url(
        latitude=float(field.Latitude) if field.Latitude is not None else None,
        longitude=float(field.Longitude) if field.Longitude is not None else None,
        boundary_geojson=field.BoundaryGeoJSON,
    )
    print(f"[biomass/satellite] gee returned: {sat}", flush=True)
    if not sat:
        raise HTTPException(
            status_code=503,
            detail="No recent cloud-free satellite imagery available for this field",
        )

    prediction = _call_estimator_url(sat["url"], source="satellite", field_id=field_id)

    try:
        captured = datetime.fromisoformat(sat["captured_at"].replace("Z", ""))
    except Exception:
        captured = datetime.utcnow()

    row = models.FieldBiomassAnalysis(
        FieldID=      field_id,
        BusinessID=   field.BusinessID,
        Source=       "satellite",
        BiomassKgHa=  prediction.get("biomass_kg_per_ha"),
        Confidence=   prediction.get("confidence"),
        ImageUrl=     sat["url"],
        CapturedAt=   captured,
        ModelVersion= prediction.get("model_version"),
        FeaturesJSON= json.dumps(prediction.get("features") or {}),
        CreatedAt=    datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_biomass_row(row)


@router.post("/fields/{field_id}/biomass/upload")
async def analyze_upload(
    field_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """User-uploaded ground-level image → estimator → stored analysis."""
    field = db.query(models.Field).filter(models.Field.FieldID == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    ext = os.path.splitext(file.filename or "upload.jpg")[1].lower() or ".jpg"
    filename = f"field{field_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"

    image_url = None
    try:
        from google.cloud import storage
        client = storage.Client()
        blob = client.bucket(BIOMASS_GCS_BUCKET).blob(f"{BIOMASS_GCS_PREFIX}/{filename}")
        blob.upload_from_string(raw, content_type=file.content_type or "image/jpeg")
        image_url = f"https://storage.googleapis.com/{BIOMASS_GCS_BUCKET}/{BIOMASS_GCS_PREFIX}/{filename}"
    except Exception as e:
        print(f"[biomass] GCS upload failed (continuing without persistent URL): {e}")

    prediction = _call_estimator_upload(
        raw, filename, file.content_type or "image/jpeg",
        source="upload", field_id=field_id,
    )

    row = models.FieldBiomassAnalysis(
        FieldID=      field_id,
        BusinessID=   field.BusinessID,
        Source=       "upload",
        BiomassKgHa=  prediction.get("biomass_kg_per_ha"),
        Confidence=   prediction.get("confidence"),
        ImageUrl=     image_url,
        CapturedAt=   datetime.utcnow(),
        ModelVersion= prediction.get("model_version"),
        FeaturesJSON= json.dumps(prediction.get("features") or {}),
        CreatedAt=    datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_biomass_row(row)
