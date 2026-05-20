"""
routers/export_compliance.py
Export compliance: customs paperwork, phytosanitary certificates, per-crop margin vs operational cost,
recall management, GlobalG.A.P./USDA Organic compliance docs.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from typing import Optional

router = APIRouter(prefix="/api/export-compliance", tags=["export_compliance"])
_ready = False


def _ensure(db: Session):
    global _ready
    if _ready:
        return
    stmts = [
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='ExportShipment')
        CREATE TABLE ExportShipment (
            ShipmentID        INT IDENTITY PRIMARY KEY,
            BusinessID        INT NOT NULL,
            ShipmentRef       NVARCHAR(100) NULL,
            ProductName       NVARCHAR(300) NOT NULL,
            HarvestLotID      NVARCHAR(100) NULL,
            DestinationCountry NVARCHAR(200) NOT NULL,
            BuyerName         NVARCHAR(300) NULL,
            QuantityKg        DECIMAL(14,3) NULL,
            PackagedUnits     INT NULL,
            DeclaredValueUSD  DECIMAL(14,2) NULL,
            ShipmentDate      DATE NULL,
            EstimatedArrival  DATE NULL,
            Status            NVARCHAR(50) NOT NULL DEFAULT 'preparing',
            Incoterms         NVARCHAR(50) NULL,
            PortOfLoading     NVARCHAR(200) NULL,
            PortOfDischarge   NVARCHAR(200) NULL,
            Notes             NVARCHAR(MAX) NULL,
            CreatedAt         DATETIME2 DEFAULT GETDATE(),
            UpdatedAt         DATETIME2 DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='PhytosanitaryCert')
        CREATE TABLE PhytosanitaryCert (
            CertID        INT IDENTITY PRIMARY KEY,
            ShipmentID    INT NOT NULL,
            BusinessID    INT NOT NULL,
            CertNumber    NVARCHAR(200) NOT NULL,
            IssuedDate    DATE NULL,
            IssuedBy      NVARCHAR(300) NULL,
            IssuingAuthority NVARCHAR(300) NULL,
            ExpiryDate    DATE NULL,
            DocumentURL   NVARCHAR(500) NULL,
            Status        NVARCHAR(50) NOT NULL DEFAULT 'active',
            Notes         NVARCHAR(MAX) NULL,
            CreatedAt     DATETIME2 DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='CustomsDocument')
        CREATE TABLE CustomsDocument (
            DocID        INT IDENTITY PRIMARY KEY,
            ShipmentID   INT NOT NULL,
            BusinessID   INT NOT NULL,
            DocType      NVARCHAR(100) NOT NULL,
            DocNumber    NVARCHAR(200) NULL,
            FiledDate    DATE NULL,
            IssuedDate   DATE NULL,
            DocumentURL  NVARCHAR(500) NULL,
            Status       NVARCHAR(50) NOT NULL DEFAULT 'pending',
            Notes        NVARCHAR(MAX) NULL,
            CreatedAt    DATETIME2 DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='ComplianceCertification')
        CREATE TABLE ComplianceCertification (
            CertID         INT IDENTITY PRIMARY KEY,
            BusinessID     INT NOT NULL,
            CertType       NVARCHAR(100) NOT NULL,
            CertNumber     NVARCHAR(200) NULL,
            IssuingBody    NVARCHAR(300) NULL,
            IssueDate      DATE NULL,
            ExpiryDate     DATE NULL,
            ScopeNotes     NVARCHAR(MAX) NULL,
            DocumentURL    NVARCHAR(500) NULL,
            Status         NVARCHAR(50) NOT NULL DEFAULT 'active',
            CreatedAt      DATETIME2 DEFAULT GETDATE(),
            UpdatedAt      DATETIME2 DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='RecallEvent')
        CREATE TABLE RecallEvent (
            RecallID       INT IDENTITY PRIMARY KEY,
            BusinessID     INT NOT NULL,
            RecallRef      NVARCHAR(100) NULL,
            ProductName    NVARCHAR(300) NOT NULL,
            AffectedLots   NVARCHAR(MAX) NULL,
            RecallReason   NVARCHAR(MAX) NOT NULL,
            Severity       NVARCHAR(50) NOT NULL DEFAULT 'voluntary',
            InitiatedDate  DATE NOT NULL,
            ResolutionDate DATE NULL,
            Status         NVARCHAR(50) NOT NULL DEFAULT 'active',
            AffectedQtyKg  DECIMAL(14,3) NULL,
            NotifiedParties NVARCHAR(MAX) NULL,
            CorrectiveActions NVARCHAR(MAX) NULL,
            Notes          NVARCHAR(MAX) NULL,
            CreatedAt      DATETIME2 DEFAULT GETDATE(),
            UpdatedAt      DATETIME2 DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='CropMarginRecord')
        CREATE TABLE CropMarginRecord (
            MarginID       INT IDENTITY PRIMARY KEY,
            BusinessID     INT NOT NULL,
            FieldID        INT NULL,
            CropName       NVARCHAR(300) NOT NULL,
            Season         NVARCHAR(100) NULL,
            HarvestedKg    DECIMAL(14,3) NULL,
            SoldKg         DECIMAL(14,3) NULL,
            RevenueUSD     DECIMAL(14,2) NULL,
            InputCostUSD   DECIMAL(14,2) NULL,
            LaborCostUSD   DECIMAL(14,2) NULL,
            OtherCostUSD   DECIMAL(14,2) NULL,
            TotalCostUSD   DECIMAL(14,2) NULL,
            GrossMarginUSD DECIMAL(14,2) NULL,
            MarginPct      DECIMAL(6,2) NULL,
            Notes          NVARCHAR(MAX) NULL,
            CreatedAt      DATETIME2 DEFAULT GETDATE()
        )""",
    ]
    for s in stmts:
        db.execute(text(s))
    db.commit()
    _ready = True


# ─── Shipments ────────────────────────────────────────────────────────────────

@router.get("/shipments")
def list_shipments(business_id: int = Query(...), status: Optional[str] = None, db: Session = Depends(get_db)):
    _ensure(db)
    q = "SELECT * FROM ExportShipment WHERE BusinessID=:bid"
    params = {"bid": business_id}
    if status:
        q += " AND Status=:st"; params["st"] = status
    q += " ORDER BY ShipmentDate DESC"
    rows = db.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/shipments")
def create_shipment(body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    count = db.execute(text("SELECT COUNT(*)+1 FROM ExportShipment WHERE BusinessID=:bid"), {"bid": body["BusinessID"]}).scalar()
    ref = f"EXP-{body['BusinessID']}-{count:04d}"
    r = db.execute(text("""
        INSERT INTO ExportShipment (BusinessID,ShipmentRef,ProductName,HarvestLotID,DestinationCountry,
            BuyerName,QuantityKg,PackagedUnits,DeclaredValueUSD,ShipmentDate,EstimatedArrival,
            Status,Incoterms,PortOfLoading,PortOfDischarge,Notes)
        OUTPUT INSERTED.ShipmentID
        VALUES (:bid,:ref,:prod,:lot,:dest,:buyer,:qty,:units,:val,:sd,:ea,:st,:inc,:pol,:pod,:notes)
    """), {
        "bid": body["BusinessID"], "ref": ref,
        "prod": body["ProductName"], "lot": body.get("HarvestLotID"),
        "dest": body["DestinationCountry"], "buyer": body.get("BuyerName"),
        "qty": body.get("QuantityKg"), "units": body.get("PackagedUnits"),
        "val": body.get("DeclaredValueUSD"), "sd": body.get("ShipmentDate"),
        "ea": body.get("EstimatedArrival"), "st": body.get("Status", "preparing"),
        "inc": body.get("Incoterms"), "pol": body.get("PortOfLoading"),
        "pod": body.get("PortOfDischarge"), "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"ShipmentID": r[0], "ShipmentRef": ref}


@router.put("/shipments/{shipment_id}/status")
def update_shipment_status(shipment_id: int, body: dict, db: Session = Depends(get_db)):
    db.execute(text("UPDATE ExportShipment SET Status=:st, UpdatedAt=GETDATE() WHERE ShipmentID=:sid AND BusinessID=:bid"),
               {"st": body["Status"], "sid": shipment_id, "bid": body["BusinessID"]})
    db.commit()
    return {"ok": True}


# ─── Phytosanitary Certificates ───────────────────────────────────────────────

@router.get("/shipments/{shipment_id}/phyto-certs")
def get_phyto(shipment_id: int, db: Session = Depends(get_db)):
    _ensure(db)
    rows = db.execute(text("SELECT * FROM PhytosanitaryCert WHERE ShipmentID=:sid ORDER BY IssuedDate DESC"),
                      {"sid": shipment_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/shipments/{shipment_id}/phyto-certs")
def add_phyto(shipment_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    r = db.execute(text("""
        INSERT INTO PhytosanitaryCert (ShipmentID,BusinessID,CertNumber,IssuedDate,IssuedBy,
            IssuingAuthority,ExpiryDate,DocumentURL,Status,Notes)
        OUTPUT INSERTED.CertID
        VALUES (:sid,:bid,:num,:idt,:by,:auth,:exp,:url,:st,:notes)
    """), {
        "sid": shipment_id, "bid": body["BusinessID"], "num": body["CertNumber"],
        "idt": body.get("IssuedDate"), "by": body.get("IssuedBy"),
        "auth": body.get("IssuingAuthority"), "exp": body.get("ExpiryDate"),
        "url": body.get("DocumentURL"), "st": body.get("Status", "active"),
        "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"CertID": r[0]}


# ─── Customs Documents ────────────────────────────────────────────────────────

@router.get("/shipments/{shipment_id}/customs-docs")
def get_customs(shipment_id: int, db: Session = Depends(get_db)):
    _ensure(db)
    rows = db.execute(text("SELECT * FROM CustomsDocument WHERE ShipmentID=:sid ORDER BY FiledDate DESC"),
                      {"sid": shipment_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/shipments/{shipment_id}/customs-docs")
def add_customs(shipment_id: int, body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    r = db.execute(text("""
        INSERT INTO CustomsDocument (ShipmentID,BusinessID,DocType,DocNumber,FiledDate,IssuedDate,DocumentURL,Status,Notes)
        OUTPUT INSERTED.DocID
        VALUES (:sid,:bid,:dt,:num,:fd,:id,:url,:st,:notes)
    """), {
        "sid": shipment_id, "bid": body["BusinessID"], "dt": body["DocType"],
        "num": body.get("DocNumber"), "fd": body.get("FiledDate"),
        "id": body.get("IssuedDate"), "url": body.get("DocumentURL"),
        "st": body.get("Status", "pending"), "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"DocID": r[0]}


# ─── Compliance Certifications (GlobalGAP / USDA Organic / etc.) ──────────────

@router.get("/certifications")
def list_compliance_certs(business_id: int = Query(...), db: Session = Depends(get_db)):
    _ensure(db)
    rows = db.execute(text("SELECT * FROM ComplianceCertification WHERE BusinessID=:bid ORDER BY ExpiryDate ASC"),
                      {"bid": business_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/certifications")
def add_compliance_cert(body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    r = db.execute(text("""
        INSERT INTO ComplianceCertification (BusinessID,CertType,CertNumber,IssuingBody,
            IssueDate,ExpiryDate,ScopeNotes,DocumentURL,Status)
        OUTPUT INSERTED.CertID
        VALUES (:bid,:ct,:num,:body,:id,:exp,:scope,:url,:st)
    """), {
        "bid": body["BusinessID"], "ct": body["CertType"], "num": body.get("CertNumber"),
        "body": body.get("IssuingBody"), "id": body.get("IssueDate"),
        "exp": body.get("ExpiryDate"), "scope": body.get("ScopeNotes"),
        "url": body.get("DocumentURL"), "st": body.get("Status", "active"),
    }).fetchone()
    db.commit()
    return {"CertID": r[0]}


@router.delete("/certifications/{cert_id}")
def delete_compliance_cert(cert_id: int, business_id: int = Query(...), db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM ComplianceCertification WHERE CertID=:cid AND BusinessID=:bid"),
               {"cid": cert_id, "bid": business_id})
    db.commit()
    return {"ok": True}


# ─── Recall Management ────────────────────────────────────────────────────────

@router.get("/recalls")
def list_recalls(business_id: int = Query(...), db: Session = Depends(get_db)):
    _ensure(db)
    rows = db.execute(text("SELECT * FROM RecallEvent WHERE BusinessID=:bid ORDER BY InitiatedDate DESC"),
                      {"bid": business_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/recalls")
def create_recall(body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    count = db.execute(text("SELECT COUNT(*)+1 FROM RecallEvent WHERE BusinessID=:bid"), {"bid": body["BusinessID"]}).scalar()
    ref = f"RCL-{body['BusinessID']}-{count:04d}"
    r = db.execute(text("""
        INSERT INTO RecallEvent (BusinessID,RecallRef,ProductName,AffectedLots,RecallReason,
            Severity,InitiatedDate,Status,AffectedQtyKg,NotifiedParties,CorrectiveActions,Notes)
        OUTPUT INSERTED.RecallID
        VALUES (:bid,:ref,:prod,:lots,:reason,:sev,:dt,:st,:qty,:notified,:actions,:notes)
    """), {
        "bid": body["BusinessID"], "ref": ref, "prod": body["ProductName"],
        "lots": body.get("AffectedLots"), "reason": body["RecallReason"],
        "sev": body.get("Severity", "voluntary"), "dt": body["InitiatedDate"],
        "st": body.get("Status", "active"), "qty": body.get("AffectedQtyKg"),
        "notified": body.get("NotifiedParties"), "actions": body.get("CorrectiveActions"),
        "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"RecallID": r[0], "RecallRef": ref}


@router.put("/recalls/{recall_id}/resolve")
def resolve_recall(recall_id: int, body: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE RecallEvent SET Status='resolved', ResolutionDate=:dt, CorrectiveActions=:actions, UpdatedAt=GETDATE()
        WHERE RecallID=:rid AND BusinessID=:bid
    """), {
        "dt": body.get("ResolutionDate"), "actions": body.get("CorrectiveActions"),
        "rid": recall_id, "bid": body["BusinessID"],
    })
    db.commit()
    return {"ok": True}


# ─── Crop Margin Records ──────────────────────────────────────────────────────

@router.get("/crop-margins")
def list_margins(business_id: int = Query(...), db: Session = Depends(get_db)):
    _ensure(db)
    rows = db.execute(text("SELECT * FROM CropMarginRecord WHERE BusinessID=:bid ORDER BY CreatedAt DESC"),
                      {"bid": business_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/crop-margins")
def create_margin(body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    inputs = float(body.get("InputCostUSD") or 0)
    labor = float(body.get("LaborCostUSD") or 0)
    other = float(body.get("OtherCostUSD") or 0)
    total_cost = inputs + labor + other
    revenue = float(body.get("RevenueUSD") or 0)
    gross_margin = revenue - total_cost
    margin_pct = round((gross_margin / revenue * 100), 2) if revenue > 0 else None
    r = db.execute(text("""
        INSERT INTO CropMarginRecord (BusinessID,FieldID,CropName,Season,HarvestedKg,SoldKg,
            RevenueUSD,InputCostUSD,LaborCostUSD,OtherCostUSD,TotalCostUSD,GrossMarginUSD,MarginPct,Notes)
        OUTPUT INSERTED.MarginID
        VALUES (:bid,:fid,:crop,:season,:hkg,:skg,:rev,:inputs,:labor,:other,:total,:gm,:pct,:notes)
    """), {
        "bid": body["BusinessID"], "fid": body.get("FieldID"),
        "crop": body["CropName"], "season": body.get("Season"),
        "hkg": body.get("HarvestedKg"), "skg": body.get("SoldKg"),
        "rev": revenue, "inputs": inputs, "labor": labor, "other": other,
        "total": total_cost, "gm": gross_margin, "pct": margin_pct,
        "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"MarginID": r[0]}


# ─── Summary ─────────────────────────────────────────────────────────────────

@router.get("/summary")
def export_summary(business_id: int = Query(...), db: Session = Depends(get_db)):
    _ensure(db)
    shipments = db.execute(text("""
        SELECT COUNT(*) AS Total,
            SUM(CASE WHEN Status='preparing' THEN 1 ELSE 0 END) AS Preparing,
            SUM(CASE WHEN Status='shipped' THEN 1 ELSE 0 END) AS Shipped,
            SUM(CASE WHEN Status='delivered' THEN 1 ELSE 0 END) AS Delivered,
            ISNULL(SUM(DeclaredValueUSD),0) AS TotalValueUSD
        FROM ExportShipment WHERE BusinessID=:bid
    """), {"bid": business_id}).fetchone()
    recalls = db.execute(text("""
        SELECT COUNT(*) AS Total, SUM(CASE WHEN Status='active' THEN 1 ELSE 0 END) AS Active
        FROM RecallEvent WHERE BusinessID=:bid
    """), {"bid": business_id}).fetchone()
    certs_expiring = db.execute(text("""
        SELECT COUNT(*) AS ExpiringIn90Days FROM ComplianceCertification
        WHERE BusinessID=:bid AND ExpiryDate IS NOT NULL
          AND ExpiryDate <= DATEADD(day,90,CAST(GETDATE() AS DATE)) AND Status='active'
    """), {"bid": business_id}).fetchone()
    margins = db.execute(text("""
        SELECT AVG(MarginPct) AS AvgMarginPct FROM CropMarginRecord WHERE BusinessID=:bid
    """), {"bid": business_id}).fetchone()
    return {
        **dict(shipments._mapping),
        "ActiveRecalls": recalls[1] if recalls else 0,
        "CertsExpiringIn90Days": certs_expiring[0] if certs_expiring else 0,
        "AvgMarginPct": float(margins[0]) if margins and margins[0] else None,
    }
