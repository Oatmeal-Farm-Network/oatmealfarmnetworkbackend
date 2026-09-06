from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from database import get_db
from datetime import date, datetime
import json
import os
import uuid
import models
from pydantic import BaseModel, validator
from typing import Optional
from geo_utils import polygon_area_hectares

router = APIRouter(prefix="/api", tags=["precision-ag"])

# ── FieldProfile table (lazy create) ─────────────────────────────────────────
_field_profile_ready = False

def _ensure_field_profile_table(db: Session):
    global _field_profile_ready
    if _field_profile_ready:
        return
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'FieldProfile')
        CREATE TABLE FieldProfile (
            ProfileID        INT IDENTITY(1,1) PRIMARY KEY,
            FieldID          INT NOT NULL,
            BusinessID       INT NOT NULL,
            SoilType         NVARCHAR(100),
            DrainageClass    NVARCHAR(100),
            SlopePercent     DECIMAL(5,2),
            Topography       NVARCHAR(100),
            OrganicMatterPct DECIMAL(5,2),
            PhLevel          DECIMAL(4,2),
            FieldNotes       NVARCHAR(MAX),
            PhotoUrls        NVARCHAR(MAX),
            UpdatedAt        DATETIME DEFAULT GETDATE()
        )
    """))
    db.commit()
    _field_profile_ready = True

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
                F.CropType, F.PlantingDate, F.BoundaryGeoJSON,
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
                "boundary_geojson":         r.BoundaryGeoJSON,
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
    # Address/Latitude/Longitude are NOT NULL columns in dbo.Field — the
    # working add-field flow (Crop Detection) always derives these from a
    # drawn boundary, but guard here too so a bad/direct API call gets a
    # clean 400 instead of a raw SQL IntegrityError.
    if field.latitude is None or field.longitude is None:
        raise HTTPException(status_code=400, detail="latitude and longitude are required")
    if not field.address:
        field.address = field.name

    try:
        planting_date = None
        if field.planting_date:
            try:
                planting_date = date.fromisoformat(field.planting_date)
            except ValueError:
                planting_date = None

        # Derive size from the drawn boundary when one is provided — the
        # polygon is the source of truth, so it overrides any user-entered
        # number. Falls back to the user value when no boundary was drawn.
        computed_size = polygon_area_hectares(field.boundary_geojson)
        size_hectares = computed_size if computed_size is not None else field.field_size_hectares

        new_field = models.Field(
            BusinessID=             field.business_id,
            Name=                   field.name,
            Address=                field.address,
            CropType=               field.crop_type,
            Latitude=               field.latitude,
            Longitude=              field.longitude,
            FieldSizeHectares=      size_hectares,
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
        existing = (
            db.query(models.Field)
            .filter(models.Field.FieldID == field_id, models.Field.DeletedAt.is_(None))
            .first()
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Field not found")
        planting_date = None
        if field.planting_date:
            try:
                planting_date = date.fromisoformat(field.planting_date)
            except ValueError:
                planting_date = None
        computed_size = polygon_area_hectares(field.boundary_geojson)
        existing.Name                   = field.name
        existing.Address                = field.address
        existing.CropType               = field.crop_type
        existing.Latitude               = field.latitude
        existing.Longitude              = field.longitude
        existing.FieldSizeHectares      = (
            computed_size if computed_size is not None else field.field_size_hectares
        )
        existing.PlantingDate           = planting_date
        # Only overwrite the saved boundary when the caller actually sent a new
        # one — an empty/omitted value (e.g. the edit form loaded without
        # re-drawing) must never wipe out a previously drawn polygon.
        if field.boundary_geojson:
            existing.BoundaryGeoJSON    = field.boundary_geojson
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
        field = (
            db.query(models.Field)
            .filter(models.Field.FieldID == field_id, models.Field.DeletedAt.is_(None))
            .first()
        )
        if not field:
            raise HTTPException(status_code=404, detail="Field not found")
        # Soft delete — permanently deleting the row would cascade-orphan (or
        # foreign-key-fail on) years of Analysis/FieldScout/FieldNote/biomass
        # history tied to this FieldID. get_fields() already filters on
        # DeletedAt, so this is enough to make the field disappear from the UI
        # while keeping the history recoverable/auditable.
        field.DeletedAt = datetime.utcnow()
        db.commit()
        return {"success": True, "deleted_id": field_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class FieldProfileUpsert(BaseModel):
    soil_type:          Optional[str] = None
    drainage_class:     Optional[str] = None
    slope_percent:      Optional[float] = None
    topography:         Optional[str] = None
    organic_matter_pct: Optional[float] = None
    ph_level:           Optional[float] = None
    field_notes:        Optional[str] = None
    photo_urls:         Optional[str] = None


@router.get("/fields/{field_id}/profile")
def get_field_profile(field_id: int, db: Session = Depends(get_db)):
    try:
        _ensure_field_profile_table(db)
        row = db.execute(text("""
            SELECT SoilType, DrainageClass, SlopePercent, Topography,
                   OrganicMatterPct, PhLevel, FieldNotes, PhotoUrls, UpdatedAt
            FROM FieldProfile WHERE FieldID = :fid
        """), {"fid": field_id}).fetchone()
        if not row:
            return {}
        return {
            "soil_type":          row.SoilType,
            "drainage_class":     row.DrainageClass,
            "slope_percent":      float(row.SlopePercent) if row.SlopePercent is not None else None,
            "topography":         row.Topography,
            "organic_matter_pct": float(row.OrganicMatterPct) if row.OrganicMatterPct is not None else None,
            "ph_level":           float(row.PhLevel) if row.PhLevel is not None else None,
            "field_notes":        row.FieldNotes,
            "photo_urls":         row.PhotoUrls,
            "updated_at":         row.UpdatedAt.isoformat() if row.UpdatedAt else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/fields/{field_id}/profile")
def upsert_field_profile(field_id: int, body: FieldProfileUpsert, business_id: int, db: Session = Depends(get_db)):
    try:
        _ensure_field_profile_table(db)
        existing = db.execute(text("SELECT ProfileID FROM FieldProfile WHERE FieldID = :fid"), {"fid": field_id}).fetchone()
        if existing:
            db.execute(text("""
                UPDATE FieldProfile SET
                    SoilType         = :soil_type,
                    DrainageClass    = :drainage_class,
                    SlopePercent     = :slope_percent,
                    Topography       = :topography,
                    OrganicMatterPct = :organic_matter_pct,
                    PhLevel          = :ph_level,
                    FieldNotes       = :field_notes,
                    PhotoUrls        = :photo_urls,
                    UpdatedAt        = GETDATE()
                WHERE FieldID = :fid
            """), {
                "fid":               field_id,
                "soil_type":          body.soil_type,
                "drainage_class":     body.drainage_class,
                "slope_percent":      body.slope_percent,
                "topography":         body.topography,
                "organic_matter_pct": body.organic_matter_pct,
                "ph_level":           body.ph_level,
                "field_notes":        body.field_notes,
                "photo_urls":         body.photo_urls,
            })
        else:
            db.execute(text("""
                INSERT INTO FieldProfile (FieldID, BusinessID, SoilType, DrainageClass, SlopePercent,
                    Topography, OrganicMatterPct, PhLevel, FieldNotes, PhotoUrls)
                VALUES (:fid, :bid, :soil_type, :drainage_class, :slope_percent,
                    :topography, :organic_matter_pct, :ph_level, :field_notes, :photo_urls)
            """), {
                "fid":               field_id,
                "bid":               business_id,
                "soil_type":          body.soil_type,
                "drainage_class":     body.drainage_class,
                "slope_percent":      body.slope_percent,
                "topography":         body.topography,
                "organic_matter_pct": body.organic_matter_pct,
                "ph_level":           body.ph_level,
                "field_notes":        body.field_notes,
                "photo_urls":         body.photo_urls,
            })
        db.commit()
        return {"ok": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/precision-ag/dashboard/summary")
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


def _call_estimator_upload(image_bytes: bytes, filename: str, content_type: str, source: str, field_id: int) -> dict:
    """Local CSIRO-inspired dual-stream estimator (no paid vision APIs)."""
    try:
        import sys
        from pathlib import Path
        from dotenv import load_dotenv

        backend_dir = Path(__file__).resolve().parent.parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        load_dotenv(backend_dir / ".env", override=True)

        # Prefer multi-domain pack, then CSIRO-only DINO pack.
        multi_pack = backend_dir / "biomass_estimator" / "calibration_multidomain.npz"
        dino_pack = backend_dir / "biomass_estimator" / "calibration_dino.npz"
        pack = multi_pack if multi_pack.is_file() else dino_pack
        if pack.is_file():
            os.environ["BIOMASS_USE_DINO"] = "true"
            os.environ["BIOMASS_CALIBRATION_PATH"] = str(pack)
            os.environ.setdefault("BIOMASS_IMG_SIZE", "518")

        # Drop stale cached calib loads from prior requests / old env
        try:
            from biomass_estimator import calibration as _calib
            _calib._load_npz.cache_clear()
        except Exception:
            pass

        from biomass_estimator import estimate_biomass_from_image
        result = estimate_biomass_from_image(image_bytes, field_id=field_id)
        if result.get("rejected"):
            raise HTTPException(
                status_code=400,
                detail=result.get("reject_reason")
                or "Photo rejected: not a pasture/crop canopy image.",
            )
        try:
            dbg = Path(backend_dir) / "biomass_estimator" / "_last_upload_debug.json"
            import json as _json
            dbg.write_text(_json.dumps({
                "model_version": result.get("model_version"),
                "calibration_mode": (result.get("features") or {}).get("calibration_mode"),
                "backbone": (result.get("features") or {}).get("backbone"),
                "stream": (result.get("features") or {}).get("stream"),
                "calib_env": os.environ.get("BIOMASS_CALIBRATION_PATH"),
                "dino_env": os.environ.get("BIOMASS_USE_DINO"),
            }, indent=2), encoding="utf-8")
        except Exception:
            pass
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Biomass estimation failed: {e}",
        ) from e


@router.get("/fields/{field_id}/biomass")
def get_biomass(field_id: int, db: Session = Depends(get_db)):
    """Latest photo-upload biomass analysis for a field. Returns empty
    payload (not 500) when the FieldBiomassAnalysis table hasn't been migrated yet."""
    field = (
        db.query(models.Field)
        .filter(models.Field.FieldID == field_id, models.Field.DeletedAt.is_(None))
        .first()
    )
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    empty = {"field_id": field_id, "upload": None, "history": []}
    try:
        latest_upload = (
            db.query(models.FieldBiomassAnalysis)
            .filter(
                models.FieldBiomassAnalysis.FieldID == field_id,
                models.FieldBiomassAnalysis.Source == "upload",
            )
            .order_by(desc(models.FieldBiomassAnalysis.CapturedAt))
            .first()
        )
        history = (
            db.query(models.FieldBiomassAnalysis)
            .filter(
                models.FieldBiomassAnalysis.FieldID == field_id,
                models.FieldBiomassAnalysis.Source == "upload",
            )
            .order_by(desc(models.FieldBiomassAnalysis.CreatedAt))
            .limit(20)
            .all()
        )
        return {
            "field_id": field_id,
            "upload": _serialize_biomass_row(latest_upload) if latest_upload else None,
            "history": [_serialize_biomass_row(r) for r in history],
        }
    except Exception as e:
        # Most common cause: FieldBiomassAnalysis table hasn't been created yet.
        print(f"[biomass] GET failed, returning empty (table missing?): {e}")
        db.rollback()
        return empty


@router.post("/fields/{field_id}/biomass/upload")
async def analyze_upload(
    field_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """User-uploaded ground-level image → estimator → stored analysis."""
    field = (
        db.query(models.Field)
        .filter(models.Field.FieldID == field_id, models.Field.DeletedAt.is_(None))
        .first()
    )
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
