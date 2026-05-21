"""
routers/outgrower.py
Contract Farming / Outgrower Management — farmer registration, contract engine,
input distribution to smallholders, buy-back workflows.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from typing import Optional
from datetime import date

router = APIRouter(prefix="/api/outgrower", tags=["outgrower"])
_ready = False


def _ensure(db: Session):
    global _ready
    if _ready:
        return
    stmts = [
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OutgrowerFarmer')
        CREATE TABLE OutgrowerFarmer (
            FarmerID          INT IDENTITY PRIMARY KEY,
            BusinessID        INT NOT NULL,
            FullName          NVARCHAR(200) NOT NULL,
            Phone             NVARCHAR(50)  NULL,
            Email             NVARCHAR(200) NULL,
            Village           NVARCHAR(200) NULL,
            District          NVARCHAR(200) NULL,
            TotalAcreage      DECIMAL(10,2) NULL,
            NationalID        NVARCHAR(100) NULL,
            BankName          NVARCHAR(200) NULL,
            BankAccount       NVARCHAR(100) NULL,
            MobileMoneyNumber NVARCHAR(100) NULL,
            Status            NVARCHAR(50)  NOT NULL DEFAULT 'active',
            JoinedDate        DATE NULL,
            Notes             NVARCHAR(MAX) NULL,
            CreatedAt         DATETIME2 DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OutgrowerContract')
        CREATE TABLE OutgrowerContract (
            ContractID      INT IDENTITY PRIMARY KEY,
            FarmerID        INT NOT NULL,
            BusinessID      INT NOT NULL,
            CropName        NVARCHAR(200) NOT NULL,
            Season          NVARCHAR(100) NULL,
            PlantingArea    DECIMAL(10,2) NULL,
            TargetQtyKg     DECIMAL(12,2) NULL,
            PricePerKg      DECIMAL(10,4) NULL,
            StartDate       DATE NULL,
            EndDate         DATE NULL,
            Status          NVARCHAR(50) NOT NULL DEFAULT 'draft',
            ContractRef     NVARCHAR(100) NULL,
            QualitySpecs    NVARCHAR(MAX) NULL,
            Notes           NVARCHAR(MAX) NULL,
            SignedDate      DATE NULL,
            CreatedAt       DATETIME2 DEFAULT GETDATE(),
            UpdatedAt       DATETIME2 DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OutgrowerInputDistribution')
        CREATE TABLE OutgrowerInputDistribution (
            DistID        INT IDENTITY PRIMARY KEY,
            ContractID    INT NOT NULL,
            FarmerID      INT NOT NULL,
            BusinessID    INT NOT NULL,
            InputType     NVARCHAR(100) NOT NULL,
            InputName     NVARCHAR(200) NOT NULL,
            Quantity      DECIMAL(10,2) NULL,
            Unit          NVARCHAR(50)  NULL,
            UnitCost      DECIMAL(10,2) NULL,
            TotalValue    DECIMAL(12,2) NULL,
            DistributedDate DATE NOT NULL,
            RecoveryMethod  NVARCHAR(100) NULL,
            Recovered       BIT DEFAULT 0,
            Notes         NVARCHAR(MAX) NULL,
            CreatedAt     DATETIME2 DEFAULT GETDATE()
        )""",
        """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OutgrowerDelivery')
        CREATE TABLE OutgrowerDelivery (
            DeliveryID      INT IDENTITY PRIMARY KEY,
            ContractID      INT NOT NULL,
            FarmerID        INT NOT NULL,
            BusinessID      INT NOT NULL,
            DeliveryDate    DATE NOT NULL,
            GrossWeightKg   DECIMAL(12,2) NULL,
            MoistureDeductKg DECIMAL(12,2) NULL,
            NetWeightKg     DECIMAL(12,2) NULL,
            QualityGrade    NVARCHAR(50)  NULL,
            PricePerKg      DECIMAL(10,4) NULL,
            GrossPayment    DECIMAL(12,2) NULL,
            InputDeductions DECIMAL(12,2) NULL,
            NetPayment      DECIMAL(12,2) NULL,
            PaymentStatus   NVARCHAR(50)  NOT NULL DEFAULT 'pending',
            PaymentDate     DATE NULL,
            WeighbridgeTicket NVARCHAR(100) NULL,
            Notes           NVARCHAR(MAX) NULL,
            CreatedAt       DATETIME2 DEFAULT GETDATE()
        )""",
    ]
    for s in stmts:
        db.execute(text(s))
    db.commit()
    _ready = True


# ─── Farmers ─────────────────────────────────────────────────────────────────

@router.get("/farmers")
def list_farmers(business_id: int = Query(...), status: Optional[str] = None, db: Session = Depends(get_db)):
    _ensure(db)
    q = "SELECT * FROM OutgrowerFarmer WHERE BusinessID=:bid"
    params = {"bid": business_id}
    if status:
        q += " AND Status=:st"; params["st"] = status
    q += " ORDER BY FullName"
    rows = db.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/farmers")
def create_farmer(body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    r = db.execute(text("""
        INSERT INTO OutgrowerFarmer (BusinessID,FullName,Phone,Email,Village,District,
            TotalAcreage,NationalID,BankName,BankAccount,MobileMoneyNumber,Status,JoinedDate,Notes)
        OUTPUT INSERTED.FarmerID
        VALUES (:bid,:name,:phone,:email,:vil,:dist,:acres,:nid,:bank,:acct,:mmn,:st,:jd,:notes)
    """), {
        "bid": body["BusinessID"], "name": body["FullName"],
        "phone": body.get("Phone"), "email": body.get("Email"),
        "vil": body.get("Village"), "dist": body.get("District"),
        "acres": body.get("TotalAcreage"), "nid": body.get("NationalID"),
        "bank": body.get("BankName"), "acct": body.get("BankAccount"),
        "mmn": body.get("MobileMoneyNumber"), "st": body.get("Status", "active"),
        "jd": body.get("JoinedDate"), "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"FarmerID": r[0]}


@router.put("/farmers/{farmer_id}")
def update_farmer(farmer_id: int, body: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OutgrowerFarmer SET FullName=:name,Phone=:phone,Email=:email,Village=:vil,
            District=:dist,TotalAcreage=:acres,NationalID=:nid,BankName=:bank,
            BankAccount=:acct,MobileMoneyNumber=:mmn,Status=:st,JoinedDate=:jd,Notes=:notes
        WHERE FarmerID=:fid AND BusinessID=:bid
    """), {
        "name": body.get("FullName"), "phone": body.get("Phone"), "email": body.get("Email"),
        "vil": body.get("Village"), "dist": body.get("District"), "acres": body.get("TotalAcreage"),
        "nid": body.get("NationalID"), "bank": body.get("BankName"), "acct": body.get("BankAccount"),
        "mmn": body.get("MobileMoneyNumber"), "st": body.get("Status"),
        "jd": body.get("JoinedDate"), "notes": body.get("Notes"),
        "fid": farmer_id, "bid": body["BusinessID"],
    })
    db.commit()
    return {"ok": True}


@router.delete("/farmers/{farmer_id}")
def delete_farmer(farmer_id: int, business_id: int = Query(...), db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OutgrowerFarmer WHERE FarmerID=:fid AND BusinessID=:bid"),
               {"fid": farmer_id, "bid": business_id})
    db.commit()
    return {"ok": True}


# ─── Contracts ────────────────────────────────────────────────────────────────

@router.get("/contracts")
def list_contracts(business_id: int = Query(...), farmer_id: Optional[int] = None, db: Session = Depends(get_db)):
    _ensure(db)
    q = """
        SELECT c.*, f.FullName AS FarmerName, f.Village
        FROM OutgrowerContract c
        JOIN OutgrowerFarmer f ON f.FarmerID=c.FarmerID
        WHERE c.BusinessID=:bid
    """
    params = {"bid": business_id}
    if farmer_id:
        q += " AND c.FarmerID=:fid"; params["fid"] = farmer_id
    q += " ORDER BY c.CreatedAt DESC"
    rows = db.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/contracts")
def create_contract(body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    r = db.execute(text("""
        INSERT INTO OutgrowerContract (FarmerID,BusinessID,CropName,Season,PlantingArea,
            TargetQtyKg,PricePerKg,StartDate,EndDate,Status,ContractRef,QualitySpecs,Notes,SignedDate)
        OUTPUT INSERTED.ContractID
        VALUES (:fid,:bid,:crop,:season,:area,:qty,:price,:sd,:ed,:st,:ref,:qs,:notes,:signed)
    """), {
        "fid": body["FarmerID"], "bid": body["BusinessID"], "crop": body["CropName"],
        "season": body.get("Season"), "area": body.get("PlantingArea"),
        "qty": body.get("TargetQtyKg"), "price": body.get("PricePerKg"),
        "sd": body.get("StartDate"), "ed": body.get("EndDate"),
        "st": body.get("Status", "draft"), "ref": body.get("ContractRef"),
        "qs": body.get("QualitySpecs"), "notes": body.get("Notes"),
        "signed": body.get("SignedDate"),
    }).fetchone()
    db.commit()
    return {"ContractID": r[0]}


@router.put("/contracts/{contract_id}/status")
def update_contract_status(contract_id: int, body: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OutgrowerContract SET Status=:st, UpdatedAt=GETDATE()
        WHERE ContractID=:cid AND BusinessID=:bid
    """), {"st": body["Status"], "cid": contract_id, "bid": body["BusinessID"]})
    db.commit()
    return {"ok": True}


# ─── Input Distribution ───────────────────────────────────────────────────────

@router.get("/distributions")
def list_distributions(business_id: int = Query(...), contract_id: Optional[int] = None, db: Session = Depends(get_db)):
    _ensure(db)
    q = """
        SELECT d.*, f.FullName AS FarmerName, c.CropName
        FROM OutgrowerInputDistribution d
        JOIN OutgrowerFarmer f ON f.FarmerID=d.FarmerID
        JOIN OutgrowerContract c ON c.ContractID=d.ContractID
        WHERE d.BusinessID=:bid
    """
    params = {"bid": business_id}
    if contract_id:
        q += " AND d.ContractID=:cid"; params["cid"] = contract_id
    q += " ORDER BY d.DistributedDate DESC"
    rows = db.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/distributions")
def create_distribution(body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    qty = body.get("Quantity") or 0
    unit_cost = body.get("UnitCost") or 0
    total = round(float(qty) * float(unit_cost), 2)
    r = db.execute(text("""
        INSERT INTO OutgrowerInputDistribution (ContractID,FarmerID,BusinessID,InputType,InputName,
            Quantity,Unit,UnitCost,TotalValue,DistributedDate,RecoveryMethod,Notes)
        OUTPUT INSERTED.DistID
        VALUES (:cid,:fid,:bid,:itype,:iname,:qty,:unit,:uc,:tv,:dt,:rm,:notes)
    """), {
        "cid": body["ContractID"], "fid": body["FarmerID"], "bid": body["BusinessID"],
        "itype": body["InputType"], "iname": body["InputName"],
        "qty": qty, "unit": body.get("Unit"), "uc": unit_cost, "tv": total,
        "dt": body["DistributedDate"], "rm": body.get("RecoveryMethod"), "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"DistID": r[0]}


# ─── Deliveries / Buy-back ────────────────────────────────────────────────────

@router.get("/deliveries")
def list_deliveries(business_id: int = Query(...), contract_id: Optional[int] = None, db: Session = Depends(get_db)):
    _ensure(db)
    q = """
        SELECT d.*, f.FullName AS FarmerName, c.CropName
        FROM OutgrowerDelivery d
        JOIN OutgrowerFarmer f ON f.FarmerID=d.FarmerID
        JOIN OutgrowerContract c ON c.ContractID=d.ContractID
        WHERE d.BusinessID=:bid
    """
    params = {"bid": business_id}
    if contract_id:
        q += " AND d.ContractID=:cid"; params["cid"] = contract_id
    q += " ORDER BY d.DeliveryDate DESC"
    rows = db.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/deliveries")
def create_delivery(body: dict, db: Session = Depends(get_db)):
    _ensure(db)
    r = db.execute(text("""
        INSERT INTO OutgrowerDelivery (ContractID,FarmerID,BusinessID,DeliveryDate,GrossWeightKg,
            MoistureDeductKg,NetWeightKg,QualityGrade,PricePerKg,GrossPayment,
            InputDeductions,NetPayment,PaymentStatus,WeighbridgeTicket,Notes)
        OUTPUT INSERTED.DeliveryID
        VALUES (:cid,:fid,:bid,:dt,:gross,:moist,:net,:grade,:ppk,:gpay,:deduct,:npay,:pst,:wbt,:notes)
    """), {
        "cid": body["ContractID"], "fid": body["FarmerID"], "bid": body["BusinessID"],
        "dt": body["DeliveryDate"],
        "gross": body.get("GrossWeightKg"), "moist": body.get("MoistureDeductKg"),
        "net": body.get("NetWeightKg"), "grade": body.get("QualityGrade"),
        "ppk": body.get("PricePerKg"), "gpay": body.get("GrossPayment"),
        "deduct": body.get("InputDeductions"), "npay": body.get("NetPayment"),
        "pst": body.get("PaymentStatus", "pending"),
        "wbt": body.get("WeighbridgeTicket"), "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"DeliveryID": r[0]}


@router.put("/deliveries/{delivery_id}/pay")
def mark_paid(delivery_id: int, body: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OutgrowerDelivery SET PaymentStatus='paid', PaymentDate=:dt
        WHERE DeliveryID=:did AND BusinessID=:bid
    """), {"dt": body.get("PaymentDate"), "did": delivery_id, "bid": body["BusinessID"]})
    db.commit()
    return {"ok": True}


# ─── Dashboard summary ────────────────────────────────────────────────────────

@router.get("/summary")
def outgrower_summary(business_id: int = Query(...), db: Session = Depends(get_db)):
    _ensure(db)
    farmers = db.execute(text(
        "SELECT COUNT(*) AS c, SUM(TotalAcreage) AS acres FROM OutgrowerFarmer WHERE BusinessID=:bid AND Status='active'"
    ), {"bid": business_id}).fetchone()
    contracts = db.execute(text(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN Status='active' THEN 1 ELSE 0 END) AS active FROM OutgrowerContract WHERE BusinessID=:bid"
    ), {"bid": business_id}).fetchone()
    deliveries = db.execute(text(
        "SELECT ISNULL(SUM(NetWeightKg),0) AS TotalKg, ISNULL(SUM(NetPayment),0) AS TotalPaid FROM OutgrowerDelivery WHERE BusinessID=:bid"
    ), {"bid": business_id}).fetchone()
    return {
        "ActiveFarmers": farmers[0] if farmers else 0,
        "TotalAcreage": float(farmers[1]) if farmers and farmers[1] else 0,
        "TotalContracts": contracts[0] if contracts else 0,
        "ActiveContracts": contracts[1] if contracts else 0,
        "TotalDeliveredKg": float(deliveries[0]) if deliveries else 0,
        "TotalPaid": float(deliveries[1]) if deliveries else 0,
    }
