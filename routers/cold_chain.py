from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/cold-chain", tags=["cold_chain"])

_tables_ready = False


def _ensure_tables(db: Session):
    global _tables_ready
    if _tables_ready:
        return
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
    db.execute(text("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE object_id = OBJECT_ID('ColdChainReading')
              AND name = 'IX_ColdChainReading_Vehicle_Time'
        )
        CREATE INDEX IX_ColdChainReading_Vehicle_Time
            ON ColdChainReading (VehicleID, RecordedAt DESC)
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'ColdChainShipment')
        CREATE TABLE ColdChainShipment (
            ShipmentID   INT IDENTITY PRIMARY KEY,
            VehicleID    INT           NOT NULL,
            BusinessID   INT           NOT NULL,
            RunDate      DATE          NOT NULL,
            RouteLabel   NVARCHAR(200) NULL,
            Status       VARCHAR(30)   NOT NULL DEFAULT 'completed',
            DriverName   NVARCHAR(200) NULL,
            DepartedAt   DATETIME2     NULL,
            ArrivedAt    DATETIME2     NULL,
            TotalMiles   DECIMAL(7,1)  NULL,
            Notes        NVARCHAR(MAX) NULL,
            CreatedAt    DATETIME2     DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'ColdChainShipmentItem')
        CREATE TABLE ColdChainShipmentItem (
            ItemID       INT IDENTITY PRIMARY KEY,
            ShipmentID   INT           NOT NULL,
            ProductName  NVARCHAR(200) NOT NULL,
            Quantity     DECIMAL(10,2) NULL,
            Unit         NVARCHAR(50)  NULL,
            Recipient    NVARCHAR(200) NULL,
            TempMinC     DECIMAL(5,2)  NULL,
            TempMaxC     DECIMAL(5,2)  NULL,
            Notes        NVARCHAR(500) NULL
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'ColdChainMaintenance')
        CREATE TABLE ColdChainMaintenance (
            MaintenanceID   INT IDENTITY PRIMARY KEY,
            VehicleID       INT           NOT NULL,
            BusinessID      INT           NOT NULL,
            ServiceDate     DATE          NOT NULL,
            ServiceType     NVARCHAR(100) NOT NULL,
            ServiceProvider NVARCHAR(200) NULL,
            Technician      NVARCHAR(200) NULL,
            Cost            DECIMAL(10,2) NULL,
            OdometerMiles   INT           NULL,
            Notes           NVARCHAR(MAX) NULL,
            NextServiceDate DATE          NULL,
            CreatedAt       DATETIME2     DEFAULT GETDATE()
        )
    """))
    db.commit()
    _tables_ready = True


def _ser(row):
    d = dict(row._mapping)
    for k, v in d.items():
        if hasattr(v, '__float__'):
            try:
                d[k] = float(v)
            except Exception:
                pass
    return d


# ── Vehicles ──────────────────────────────────────────────────────────────────

@router.get("/vehicles")
def list_vehicles(business_id: int = Query(...), db: Session = Depends(get_db)):
    _ensure_tables(db)
    rows = db.execute(
        text("""
            SELECT v.VehicleID, v.BusinessID, v.VehicleName, v.LicensePlate,
                   v.DriverName, v.DriverPhone, v.MinTempC, v.MaxTempC,
                   v.IsActive, v.CreatedAt,
                   lr.TempC    AS LatestTempC,
                   lr.RecordedAt AS LatestReadingAt
            FROM ColdChainVehicle v
            OUTER APPLY (
                SELECT TOP 1 TempC, RecordedAt
                FROM ColdChainReading
                WHERE VehicleID = v.VehicleID
                ORDER BY RecordedAt DESC
            ) lr
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
    db.execute(text("DELETE FROM ColdChainReading      WHERE VehicleID = :vid"), {"vid": vehicle_id})
    db.execute(text("""
        DELETE ci FROM ColdChainShipmentItem ci
        JOIN ColdChainShipment s ON ci.ShipmentID = s.ShipmentID
        WHERE s.VehicleID = :vid
    """), {"vid": vehicle_id})
    db.execute(text("DELETE FROM ColdChainShipment     WHERE VehicleID = :vid"), {"vid": vehicle_id})
    db.execute(text("DELETE FROM ColdChainMaintenance  WHERE VehicleID = :vid"), {"vid": vehicle_id})
    db.execute(text("DELETE FROM ColdChainVehicle      WHERE VehicleID = :vid"), {"vid": vehicle_id})
    db.commit()
    return {"ok": True}


# ── Readings ──────────────────────────────────────────────────────────────────

@router.get("/vehicles/{vehicle_id}/readings")
def list_readings(
    vehicle_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    _ensure_tables(db)
    rows = db.execute(
        text(f"""
            SELECT TOP {limit} ReadingID, VehicleID, TempC, Humidity,
                   LocationDesc, RecordedAt, Notes
            FROM ColdChainReading
            WHERE VehicleID = :vid
            ORDER BY RecordedAt DESC
        """),
        {"vid": vehicle_id},
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


# ── Shipments ─────────────────────────────────────────────────────────────────

@router.get("/vehicles/{vehicle_id}/shipments")
def list_shipments(
    vehicle_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    _ensure_tables(db)
    rows = db.execute(
        text(f"""
            SELECT TOP {limit}
                s.ShipmentID, s.VehicleID, s.BusinessID, s.RunDate, s.RouteLabel,
                s.Status, s.DriverName, s.DepartedAt, s.ArrivedAt,
                s.TotalMiles, s.Notes, s.CreatedAt,
                COUNT(i.ItemID) AS ItemCount
            FROM ColdChainShipment s
            LEFT JOIN ColdChainShipmentItem i ON i.ShipmentID = s.ShipmentID
            WHERE s.VehicleID = :vid
            GROUP BY s.ShipmentID, s.VehicleID, s.BusinessID, s.RunDate, s.RouteLabel,
                     s.Status, s.DriverName, s.DepartedAt, s.ArrivedAt,
                     s.TotalMiles, s.Notes, s.CreatedAt
            ORDER BY s.RunDate DESC
        """),
        {"vid": vehicle_id},
    ).fetchall()
    return [_ser(r) for r in rows]


@router.post("/vehicles/{vehicle_id}/shipments")
def create_shipment(vehicle_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure_tables(db)
    if not body.get("RunDate"):
        raise HTTPException(400, "RunDate is required")
    if not body.get("BusinessID"):
        raise HTTPException(400, "BusinessID is required")
    row = db.execute(
        text("""
            INSERT INTO ColdChainShipment
                (VehicleID, BusinessID, RunDate, RouteLabel, Status,
                 DriverName, DepartedAt, ArrivedAt, TotalMiles, Notes)
            OUTPUT INSERTED.ShipmentID
            VALUES (:vid, :bid, :date, :label, :status,
                    :driver, :dep, :arr, :miles, :notes)
        """),
        {
            "vid":    vehicle_id,
            "bid":    body["BusinessID"],
            "date":   body["RunDate"],
            "label":  body.get("RouteLabel"),
            "status": body.get("Status", "completed"),
            "driver": body.get("DriverName"),
            "dep":    body.get("DepartedAt"),
            "arr":    body.get("ArrivedAt"),
            "miles":  body.get("TotalMiles"),
            "notes":  body.get("Notes"),
        },
    ).fetchone()
    shipment_id = row[0]

    # Insert items if provided
    for item in body.get("Items", []):
        db.execute(text("""
            INSERT INTO ColdChainShipmentItem
                (ShipmentID, ProductName, Quantity, Unit, Recipient, TempMinC, TempMaxC, Notes)
            VALUES (:sid, :name, :qty, :unit, :recip, :tmin, :tmax, :notes)
        """), {
            "sid":   shipment_id,
            "name":  item.get("ProductName", ""),
            "qty":   item.get("Quantity"),
            "unit":  item.get("Unit"),
            "recip": item.get("Recipient"),
            "tmin":  item.get("TempMinC"),
            "tmax":  item.get("TempMaxC"),
            "notes": item.get("Notes"),
        })

    db.commit()
    return {"ShipmentID": shipment_id}


@router.get("/shipments/{shipment_id}")
def get_shipment(shipment_id: int, db: Session = Depends(get_db)):
    _ensure_tables(db)
    s = db.execute(
        text("SELECT * FROM ColdChainShipment WHERE ShipmentID = :sid"),
        {"sid": shipment_id},
    ).fetchone()
    if not s:
        raise HTTPException(404, "Shipment not found")
    result = _ser(s)
    items = db.execute(
        text("SELECT * FROM ColdChainShipmentItem WHERE ShipmentID = :sid ORDER BY ItemID"),
        {"sid": shipment_id},
    ).fetchall()
    result["Items"] = [_ser(i) for i in items]
    return result


@router.post("/shipments/{shipment_id}/items")
def add_shipment_item(shipment_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure_tables(db)
    if not body.get("ProductName"):
        raise HTTPException(400, "ProductName is required")
    row = db.execute(
        text("""
            INSERT INTO ColdChainShipmentItem
                (ShipmentID, ProductName, Quantity, Unit, Recipient, TempMinC, TempMaxC, Notes)
            OUTPUT INSERTED.ItemID
            VALUES (:sid, :name, :qty, :unit, :recip, :tmin, :tmax, :notes)
        """),
        {
            "sid":   shipment_id,
            "name":  body["ProductName"],
            "qty":   body.get("Quantity"),
            "unit":  body.get("Unit"),
            "recip": body.get("Recipient"),
            "tmin":  body.get("TempMinC"),
            "tmax":  body.get("TempMaxC"),
            "notes": body.get("Notes"),
        },
    ).fetchone()
    db.commit()
    return {"ItemID": row[0]}


@router.patch("/shipments/{shipment_id}")
def update_shipment(shipment_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure_tables(db)
    db.execute(text("""
        UPDATE ColdChainShipment SET
            RouteLabel  = COALESCE(:label,  RouteLabel),
            Status      = COALESCE(:status, Status),
            DriverName  = COALESCE(:driver, DriverName),
            DepartedAt  = COALESCE(:dep,    DepartedAt),
            ArrivedAt   = COALESCE(:arr,    ArrivedAt),
            TotalMiles  = COALESCE(:miles,  TotalMiles),
            Notes       = COALESCE(:notes,  Notes)
        WHERE ShipmentID = :sid
    """), {
        "sid":    shipment_id,
        "label":  body.get("RouteLabel"),
        "status": body.get("Status"),
        "driver": body.get("DriverName"),
        "dep":    body.get("DepartedAt"),
        "arr":    body.get("ArrivedAt"),
        "miles":  body.get("TotalMiles"),
        "notes":  body.get("Notes"),
    })
    db.commit()
    return {"ok": True}


@router.delete("/shipments/{shipment_id}")
def delete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    _ensure_tables(db)
    db.execute(text("DELETE FROM ColdChainShipmentItem WHERE ShipmentID = :sid"), {"sid": shipment_id})
    db.execute(text("DELETE FROM ColdChainShipment     WHERE ShipmentID = :sid"), {"sid": shipment_id})
    db.commit()
    return {"ok": True}


# ── Maintenance ───────────────────────────────────────────────────────────────

@router.get("/vehicles/{vehicle_id}/maintenance")
def list_maintenance(vehicle_id: int, db: Session = Depends(get_db)):
    _ensure_tables(db)
    rows = db.execute(
        text("""
            SELECT * FROM ColdChainMaintenance
            WHERE VehicleID = :vid
            ORDER BY ServiceDate DESC
        """),
        {"vid": vehicle_id},
    ).fetchall()
    return [_ser(r) for r in rows]


@router.post("/vehicles/{vehicle_id}/maintenance")
def add_maintenance(vehicle_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure_tables(db)
    if not body.get("ServiceDate") or not body.get("ServiceType"):
        raise HTTPException(400, "ServiceDate and ServiceType are required")
    if not body.get("BusinessID"):
        raise HTTPException(400, "BusinessID is required")
    row = db.execute(
        text("""
            INSERT INTO ColdChainMaintenance
                (VehicleID, BusinessID, ServiceDate, ServiceType, ServiceProvider,
                 Technician, Cost, OdometerMiles, Notes, NextServiceDate)
            OUTPUT INSERTED.MaintenanceID
            VALUES (:vid, :bid, :date, :stype, :provider,
                    :tech, :cost, :odo, :notes, :next)
        """),
        {
            "vid":      vehicle_id,
            "bid":      body["BusinessID"],
            "date":     body["ServiceDate"],
            "stype":    body["ServiceType"],
            "provider": body.get("ServiceProvider"),
            "tech":     body.get("Technician"),
            "cost":     body.get("Cost"),
            "odo":      body.get("OdometerMiles"),
            "notes":    body.get("Notes"),
            "next":     body.get("NextServiceDate"),
        },
    ).fetchone()
    db.commit()
    return {"MaintenanceID": row[0]}


@router.patch("/maintenance/{maintenance_id}")
def update_maintenance(maintenance_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure_tables(db)
    db.execute(text("""
        UPDATE ColdChainMaintenance SET
            ServiceType     = COALESCE(:stype,    ServiceType),
            ServiceProvider = COALESCE(:provider, ServiceProvider),
            Technician      = COALESCE(:tech,     Technician),
            Cost            = COALESCE(:cost,     Cost),
            OdometerMiles   = COALESCE(:odo,      OdometerMiles),
            Notes           = COALESCE(:notes,    Notes),
            NextServiceDate = COALESCE(:next,     NextServiceDate)
        WHERE MaintenanceID = :mid
    """), {
        "mid":      maintenance_id,
        "stype":    body.get("ServiceType"),
        "provider": body.get("ServiceProvider"),
        "tech":     body.get("Technician"),
        "cost":     body.get("Cost"),
        "odo":      body.get("OdometerMiles"),
        "notes":    body.get("Notes"),
        "next":     body.get("NextServiceDate"),
    })
    db.commit()
    return {"ok": True}


@router.delete("/maintenance/{maintenance_id}")
def delete_maintenance(maintenance_id: int, db: Session = Depends(get_db)):
    _ensure_tables(db)
    db.execute(text("DELETE FROM ColdChainMaintenance WHERE MaintenanceID = :mid"), {"mid": maintenance_id})
    db.commit()
    return {"ok": True}
