from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from datetime import date, datetime
import models
from pydantic import BaseModel, validator
from typing import Optional

router = APIRouter(prefix="/api", tags=["precision-ag"])


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
        fields = (
            db.query(models.Field)
            .filter(models.Field.BusinessID == business_id)
            .order_by(models.Field.Name)
            .all()
        )
        return [
            {
                "fieldid":                  f.FieldID,
                "id":                       f.FieldID,
                "business_id":              f.BusinessID,
                "name":                     f.Name,
                "address":                  f.Address,
                "latitude":                 float(f.Latitude) if f.Latitude else None,
                "longitude":                float(f.Longitude) if f.Longitude else None,
                "field_size_hectares":      float(f.FieldSizeHectares) if f.FieldSizeHectares else None,
                "crop_type":                f.CropType,
                "planting_date":            str(f.PlantingDate) if f.PlantingDate else None,
                "monitoring_enabled":       bool(f.MonitoringEnabled) if f.MonitoringEnabled is not None else True,
                "monitoring_interval_days": f.MonitoringIntervalDays,
                "alert_threshold_health":   f.AlertThresholdHealth,
            }
            for f in fields
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