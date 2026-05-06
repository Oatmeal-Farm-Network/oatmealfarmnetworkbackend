from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/cold-chain", tags=["cold_chain"])


def _ensure_tables(db: Session):
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'ColdChainVehicle')
        CREATE TABLE ColdChainVehicle (
            VehicleID     INT IDENTITY PRIMARY KEY,
            BusinessID    INT NOT NULL,
            VehicleName   NVARCHAR(200) NOT NULL,
            LicensePlate  NVARCHAR(50)  NULL,
            DriverName    NVARCHAR(200) NULL,
            DriverPhone   NVARCHAR(50)  NULL,
            MinTempC      DECIMAL(5,2)  NOT NULL DEFAULT -2.0,
            MaxTempC      DECIMAL(5,2)  NOT NULL DEFAULT 7.0,
            IsActive      BIT           NOT NULL DEFAULT 1,
            CreatedAt     DATETIME2     DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'ColdChainReading')
        CREATE TABLE ColdChainReading (
            ReadingID    INT IDENTITY PRIMARY KEY,
            VehicleID    INT           NOT NULL,
            TempC        DECIMAL(5,2)  NOT NULL,
            Humidity     DECIMAL(5,2)  NULL,
            LocationDesc NVARCHAR(500) NULL,
            RecordedAt   DATETIME2     NOT NULL DEFAULT GETDATE(),
            Notes        NVARCHAR(1000) NULL
        )
    """))
    db.commit()


# ── Vehicles ──────────────────────────────────────────────────────────────────

@router.get("/vehicles")
def list_vehicles(business_id: int = Query(...), db: Session = Depends(get_db)):
    _ensure_tables(db)
    rows = db.execute(
        text("""
            SELECT v.*, (
                SELECT TOP 1 TempC FROM ColdChainReading
                WHERE VehicleID = v.VehicleID ORDER BY RecordedAt DESC
            ) AS LatestTempC,
            (
                SELECT TOP 1 RecordedAt FROM ColdChainReading
                WHERE VehicleID = v.VehicleID ORDER BY RecordedAt DESC
            ) AS LatestReadingAt
            FROM ColdChainVehicle v
            WHERE v.BusinessID = :bid
            ORDER BY v.VehicleName
        """),
        {"bid": business_id},
    ).fetchall()
    cols = ["VehicleID", "BusinessID", "VehicleName", "LicensePlate",
            "DriverName", "DriverPhone", "MinTempC", "MaxTempC", "IsActive",
            "CreatedAt", "LatestTempC", "LatestReadingAt"]
    return [dict(zip(cols, r)) for r in rows]


@router.post("/vehicles")
def create_vehicle(body: dict, db: Session = Depends(get_db)):
    _ensure_tables(db)
    required = ["BusinessID", "VehicleName"]
    for f in required:
        if not body.get(f):
            raise HTTPException(400, f"{f} is required")
    row = db.execute(
        text("""
            INSERT INTO ColdChainVehicle
                (BusinessID, VehicleName, LicensePlate, DriverName, DriverPhone, MinTempC, MaxTempC)
            OUTPUT INSERTED.*
            VALUES (:bid, :name, :plate, :driver, :phone, :min_t, :max_t)
        """),
        {
            "bid":    body["BusinessID"],
            "name":   body["VehicleName"],
            "plate":  body.get("LicensePlate"),
            "driver": body.get("DriverName"),
            "phone":  body.get("DriverPhone"),
            "min_t":  body.get("MinTempC", -2.0),
            "max_t":  body.get("MaxTempC", 7.0),
        },
    ).fetchone()
    db.commit()
    return {"VehicleID": row[0]}


@router.put("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure_tables(db)
    db.execute(
        text("""
            UPDATE ColdChainVehicle SET
                VehicleName  = COALESCE(:name,   VehicleName),
                LicensePlate = COALESCE(:plate,  LicensePlate),
                DriverName   = COALESCE(:driver, DriverName),
                DriverPhone  = COALESCE(:phone,  DriverPhone),
                MinTempC     = COALESCE(:min_t,  MinTempC),
                MaxTempC     = COALESCE(:max_t,  MaxTempC),
                IsActive     = COALESCE(:active, IsActive)
            WHERE VehicleID = :vid
        """),
        {
            "vid":    vehicle_id,
            "name":   body.get("VehicleName"),
            "plate":  body.get("LicensePlate"),
            "driver": body.get("DriverName"),
            "phone":  body.get("DriverPhone"),
            "min_t":  body.get("MinTempC"),
            "max_t":  body.get("MaxTempC"),
            "active": body.get("IsActive"),
        },
    )
    db.commit()
    return {"ok": True}


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    _ensure_tables(db)
    db.execute(text("DELETE FROM ColdChainReading WHERE VehicleID = :vid"), {"vid": vehicle_id})
    db.execute(text("DELETE FROM ColdChainVehicle  WHERE VehicleID = :vid"), {"vid": vehicle_id})
    db.commit()
    return {"ok": True}


# ── Readings ──────────────────────────────────────────────────────────────────

@router.get("/vehicles/{vehicle_id}/readings")
def list_readings(
    vehicle_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    _ensure_tables(db)
    rows = db.execute(
        text("""
            SELECT TOP (@lim) ReadingID, VehicleID, TempC, Humidity,
                   LocationDesc, RecordedAt, Notes
            FROM ColdChainReading
            WHERE VehicleID = :vid
            ORDER BY RecordedAt DESC
        """),
        {"vid": vehicle_id, "lim": limit},
    ).fetchall()
    cols = ["ReadingID", "VehicleID", "TempC", "Humidity", "LocationDesc", "RecordedAt", "Notes"]
    return [dict(zip(cols, r)) for r in rows]


@router.post("/vehicles/{vehicle_id}/readings")
def add_reading(vehicle_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure_tables(db)
    if body.get("TempC") is None:
        raise HTTPException(400, "TempC is required")
    row = db.execute(
        text("""
            INSERT INTO ColdChainReading (VehicleID, TempC, Humidity, LocationDesc, Notes)
            OUTPUT INSERTED.ReadingID
            VALUES (:vid, :temp, :hum, :loc, :notes)
        """),
        {
            "vid":   vehicle_id,
            "temp":  body["TempC"],
            "hum":   body.get("Humidity"),
            "loc":   body.get("LocationDesc"),
            "notes": body.get("Notes"),
        },
    ).fetchone()
    db.commit()
    return {"ReadingID": row[0]}
