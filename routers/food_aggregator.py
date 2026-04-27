"""
Food Aggregator tools — back-end for the Farm2Fam-style direct-procurement model.

Aggregators sign farms onto contracts (often supplying inputs like saplings or
tunnels in exchange for first-right of harvest), buy the produce themselves
(taking inventory + market risk), then push it through B2B (retail chains,
restaurants) and D2C (own storefront, Zepto/Swiggy-style instant commerce)
channels — moving everything via a cold chain they own.

Schema (all tables OFNAggregator*, scoped by BusinessID = the aggregator):

  OFNAggregatorFarm           Partner farm registry
  OFNAggregatorContract       Per-farm contract (first-right / obligation, terms)
  OFNAggregatorInput          Inputs distributed to farms (saplings, tunnels, fertilizer)
  OFNAggregatorPurchase       Goods receipt — farm → aggregator (with residue test)
  OFNAggregatorInventory      What's currently in cold storage (links to a Purchase)
  OFNAggregatorB2BAccount     Retail/restaurant/distributor buyer accounts
  OFNAggregatorB2BOrder       B2B sales orders
  OFNAggregatorD2COrder       D2C orders (own storefront + delivery-app channels)
  OFNAggregatorLogistics      Delivery dispatch w/ cold-chain temp logging
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database import get_db, SessionLocal

router = APIRouter()


def ensure_tables(db: Session):
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorFarm')
        CREATE TABLE OFNAggregatorFarm (
            FarmID         INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID     INT NOT NULL,                  -- aggregator's BusinessID
            FarmName       NVARCHAR(255) NOT NULL,
            ContactName    NVARCHAR(150),
            ContactPhone   NVARCHAR(60),
            ContactEmail   NVARCHAR(255),
            AddressLine    NVARCHAR(255),
            City           NVARCHAR(120),
            Region         NVARCHAR(120),                 -- state / province
            Country        NVARCHAR(120),
            HectaresUnder  DECIMAL(10,2),
            PrimaryCrops   NVARCHAR(500),                 -- comma-list e.g. "blueberry, strawberry"
            Certification  NVARCHAR(120),                 -- organic / residue-free / GAP / none
            Status         NVARCHAR(40) DEFAULT 'active', -- active / paused / churned
            JoinedDate     DATE DEFAULT CONVERT(DATE, GETDATE()),
            Notes          NVARCHAR(MAX),
            CreatedDate    DATETIME DEFAULT GETDATE(),
            UpdatedDate    DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorContract')
        CREATE TABLE OFNAggregatorContract (
            ContractID         INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID         INT NOT NULL,
            FarmID             INT NOT NULL,
            CropType           NVARCHAR(120) NOT NULL,    -- "blueberry", "strawberry"
            ContractType       NVARCHAR(40) DEFAULT 'first_right', -- first_right / obligation / spot
            PricingModel       NVARCHAR(40) DEFAULT 'fixed',       -- fixed / floor_with_share / market_minus
            PricePerKg         DECIMAL(10,2),
            EstimatedKgPerSeason DECIMAL(12,2),
            StartDate          DATE,
            EndDate            DATE,
            ResidueRequirement NVARCHAR(120),             -- "residue-free" / "EU MRL" / etc.
            Terms              NVARCHAR(MAX),
            Status             NVARCHAR(40) DEFAULT 'active',  -- active / completed / breached / cancelled
            CreatedDate        DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorInput')
        CREATE TABLE OFNAggregatorInput (
            InputID         INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID      INT NOT NULL,
            FarmID          INT NOT NULL,
            InputType       NVARCHAR(60) NOT NULL,        -- sapling / tunnel / fertilizer / pesticide / equipment / training
            Description     NVARCHAR(500),
            Quantity        DECIMAL(12,2),
            Unit            NVARCHAR(40),                 -- units / kg / sqft / sessions
            UnitCost        DECIMAL(10,2),
            TotalCost       DECIMAL(12,2),
            ProvidedDate    DATE DEFAULT CONVERT(DATE, GETDATE()),
            RecoveryModel   NVARCHAR(40) DEFAULT 'deduct_from_payout', -- deduct_from_payout / grant / loan
            Notes           NVARCHAR(MAX),
            CreatedDate     DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorPurchase')
        CREATE TABLE OFNAggregatorPurchase (
            PurchaseID       INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID       INT NOT NULL,
            FarmID           INT NOT NULL,
            ContractID       INT NULL,                    -- nullable for spot buys
            CropType         NVARCHAR(120) NOT NULL,
            Grade            NVARCHAR(40),                -- premium / standard / processing
            QuantityKg       DECIMAL(12,2) NOT NULL,
            PricePerKg       DECIMAL(10,2),
            TotalPaid        DECIMAL(12,2),
            ResidueTestStatus NVARCHAR(40) DEFAULT 'pending', -- pending / passed / failed
            ResidueTestNotes NVARCHAR(500),
            HarvestDate      DATE,
            ReceivedDate     DATE DEFAULT CONVERT(DATE, GETDATE()),
            PaymentStatus    NVARCHAR(40) DEFAULT 'unpaid', -- unpaid / partial / paid
            CreatedDate      DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorInventory')
        CREATE TABLE OFNAggregatorInventory (
            InventoryID      INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID       INT NOT NULL,
            PurchaseID       INT NOT NULL,                -- source goods receipt
            CropType         NVARCHAR(120),               -- denormalized for fast lookup
            CurrentKg        DECIMAL(12,2) NOT NULL,
            ColdStorageUnit  NVARCHAR(60),                -- chamber / bay
            TargetTempC      DECIMAL(5,2),
            CurrentTempC     DECIMAL(5,2),
            QCStatus         NVARCHAR(40) DEFAULT 'ok',   -- ok / hold / quarantine / discarded
            ExpiryDate       DATE,
            UpdatedDate      DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorB2BAccount')
        CREATE TABLE OFNAggregatorB2BAccount (
            AccountID       INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID      INT NOT NULL,
            BuyerName       NVARCHAR(255) NOT NULL,
            BuyerType       NVARCHAR(40) DEFAULT 'retail', -- retail / restaurant / distributor / institution
            ContactName     NVARCHAR(150),
            ContactPhone    NVARCHAR(60),
            ContactEmail    NVARCHAR(255),
            DeliveryAddress NVARCHAR(500),
            NetTermsDays    INT DEFAULT 30,
            CreditLimit     DECIMAL(12,2),
            Status          NVARCHAR(40) DEFAULT 'active', -- active / on_hold / churned
            Notes           NVARCHAR(MAX),
            CreatedDate     DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorB2BOrder')
        CREATE TABLE OFNAggregatorB2BOrder (
            OrderID         INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID      INT NOT NULL,
            AccountID       INT NOT NULL,
            OrderDate       DATE DEFAULT CONVERT(DATE, GETDATE()),
            CropType        NVARCHAR(120),
            QuantityKg      DECIMAL(12,2),
            PricePerKg      DECIMAL(10,2),
            TotalValue      DECIMAL(12,2),
            DeliveryDate    DATE,
            Status          NVARCHAR(40) DEFAULT 'placed', -- placed / picking / dispatched / delivered / cancelled
            InvoiceNumber   NVARCHAR(60),
            PaymentStatus   NVARCHAR(40) DEFAULT 'unpaid',
            Notes           NVARCHAR(MAX),
            CreatedDate     DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorD2COrder')
        CREATE TABLE OFNAggregatorD2COrder (
            OrderID         INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID      INT NOT NULL,
            Channel         NVARCHAR(40) DEFAULT 'own_app', -- own_app / zepto / swiggy / blinkit / amazon / other
            ExternalOrderID NVARCHAR(120),                  -- channel's order reference
            CustomerName    NVARCHAR(255),
            CustomerPhone   NVARCHAR(60),
            DeliveryAddress NVARCHAR(500),
            CropType        NVARCHAR(120),
            QuantityKg      DECIMAL(10,2),
            TotalValue      DECIMAL(10,2),
            OrderDate       DATETIME DEFAULT GETDATE(),
            DeliverySLAMinutes INT,                         -- e.g. 30 for instant-commerce
            Status          NVARCHAR(40) DEFAULT 'placed',  -- placed / picking / out_for_delivery / delivered / refunded
            CreatedDate     DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='OFNAggregatorLogistics')
        CREATE TABLE OFNAggregatorLogistics (
            DispatchID      INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID      INT NOT NULL,
            OrderType       NVARCHAR(10) NOT NULL,          -- 'b2b' / 'd2c' / 'inbound'
            OrderID         INT NULL,                        -- references B2BOrder.OrderID, D2COrder.OrderID, or Purchase.PurchaseID
            VehicleID       NVARCHAR(60),                    -- registration / fleet ID
            DriverName      NVARCHAR(150),
            DriverPhone     NVARCHAR(60),
            PickupTime      DATETIME,
            DeliveryTime    DATETIME,
            ColdChainTempC  DECIMAL(5,2),                    -- max temp seen in transit
            ColdChainBreach BIT DEFAULT 0,                   -- did temp exceed threshold
            RouteNotes      NVARCHAR(MAX),
            Status          NVARCHAR(40) DEFAULT 'scheduled',-- scheduled / in_transit / delivered / failed
            CreatedDate     DATETIME DEFAULT GETDATE()
        )
    """))

    # Indexes for the per-business queries every screen runs
    for ix in [
        ("IX_OFNAggregatorFarm_Biz",       "OFNAggregatorFarm",      "BusinessID"),
        ("IX_OFNAggregatorContract_Biz",   "OFNAggregatorContract",  "BusinessID"),
        ("IX_OFNAggregatorInput_Biz",      "OFNAggregatorInput",     "BusinessID"),
        ("IX_OFNAggregatorPurchase_Biz",   "OFNAggregatorPurchase",  "BusinessID"),
        ("IX_OFNAggregatorInventory_Biz",  "OFNAggregatorInventory", "BusinessID"),
        ("IX_OFNAggregatorB2BAccount_Biz", "OFNAggregatorB2BAccount","BusinessID"),
        ("IX_OFNAggregatorB2BOrder_Biz",   "OFNAggregatorB2BOrder",  "BusinessID"),
        ("IX_OFNAggregatorD2COrder_Biz",   "OFNAggregatorD2COrder",  "BusinessID"),
        ("IX_OFNAggregatorLogistics_Biz",  "OFNAggregatorLogistics", "BusinessID"),
    ]:
        name, table, col = ix
        db.execute(text(f"""
            IF NOT EXISTS (SELECT 1 FROM sys.indexes
                            WHERE name='{name}' AND object_id = OBJECT_ID('{table}'))
            CREATE INDEX {name} ON {table} ({col})
        """))
    db.commit()


try:
    with SessionLocal() as _db:
        ensure_tables(_db)
except Exception as e:
    print(f"[food_aggregator] Table ensure warning: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Hub dashboard summary — KPIs across every subdashboard for the landing page
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/aggregator/{business_id}/dashboard")
def hub_dashboard(business_id: int, db: Session = Depends(get_db)):
    bid = {"bid": business_id}
    farms_active = db.execute(text(
        "SELECT COUNT(*) FROM OFNAggregatorFarm WHERE BusinessID = :bid AND Status = 'active'"
    ), bid).scalar() or 0
    contracts_active = db.execute(text(
        "SELECT COUNT(*) FROM OFNAggregatorContract WHERE BusinessID = :bid AND Status = 'active'"
    ), bid).scalar() or 0
    inputs_30d = db.execute(text(
        "SELECT ISNULL(SUM(TotalCost),0) FROM OFNAggregatorInput "
        "WHERE BusinessID = :bid AND ProvidedDate >= DATEADD(DAY,-30,CONVERT(DATE,GETDATE()))"
    ), bid).scalar() or 0
    purchases_30d = db.execute(text(
        "SELECT ISNULL(SUM(TotalPaid),0), ISNULL(SUM(QuantityKg),0) FROM OFNAggregatorPurchase "
        "WHERE BusinessID = :bid AND ReceivedDate >= DATEADD(DAY,-30,CONVERT(DATE,GETDATE()))"
    ), bid).fetchone()
    inventory_kg = db.execute(text(
        "SELECT ISNULL(SUM(CurrentKg),0) FROM OFNAggregatorInventory "
        "WHERE BusinessID = :bid AND QCStatus IN ('ok','hold')"
    ), bid).scalar() or 0
    inventory_hold = db.execute(text(
        "SELECT COUNT(*) FROM OFNAggregatorInventory "
        "WHERE BusinessID = :bid AND QCStatus IN ('hold','quarantine')"
    ), bid).scalar() or 0
    b2b_30d = db.execute(text(
        "SELECT ISNULL(SUM(TotalValue),0), COUNT(*) FROM OFNAggregatorB2BOrder "
        "WHERE BusinessID = :bid AND OrderDate >= DATEADD(DAY,-30,CONVERT(DATE,GETDATE()))"
    ), bid).fetchone()
    d2c_30d = db.execute(text(
        "SELECT ISNULL(SUM(TotalValue),0), COUNT(*) FROM OFNAggregatorD2COrder "
        "WHERE BusinessID = :bid AND OrderDate >= DATEADD(DAY,-30,GETDATE())"
    ), bid).fetchone()
    d2c_by_channel = db.execute(text(
        "SELECT Channel, COUNT(*) AS Orders, ISNULL(SUM(TotalValue),0) AS Revenue "
        "FROM OFNAggregatorD2COrder "
        "WHERE BusinessID = :bid AND OrderDate >= DATEADD(DAY,-30,GETDATE()) "
        "GROUP BY Channel ORDER BY Revenue DESC"
    ), bid).fetchall()
    cold_chain_breaches_7d = db.execute(text(
        "SELECT COUNT(*) FROM OFNAggregatorLogistics "
        "WHERE BusinessID = :bid AND ColdChainBreach = 1 "
        "  AND CreatedDate >= DATEADD(DAY,-7,GETDATE())"
    ), bid).scalar() or 0
    return {
        "farms": {"active": farms_active},
        "contracts": {"active": contracts_active},
        "inputs": {"cost_30d": float(inputs_30d)},
        "purchases": {
            "spend_30d": float(purchases_30d[0] or 0),
            "kg_30d":    float(purchases_30d[1] or 0),
        },
        "inventory": {
            "current_kg":   float(inventory_kg),
            "items_on_hold": int(inventory_hold),
        },
        "sales": {
            "b2b_revenue_30d": float(b2b_30d[0] or 0),
            "b2b_orders_30d":  int(b2b_30d[1] or 0),
            "d2c_revenue_30d": float(d2c_30d[0] or 0),
            "d2c_orders_30d":  int(d2c_30d[1] or 0),
            "d2c_by_channel":  [dict(r._mapping) for r in d2c_by_channel],
        },
        "logistics": {
            "cold_chain_breaches_7d": int(cold_chain_breaches_7d),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper — generic single-row update that whitelists allowed columns
# ─────────────────────────────────────────────────────────────────────────────

def _update_row(db, table, pk_col, pk_val, body, allowed):
    """UPDATE ... SET col = :col ... WHERE pk_col = :pk for whitelisted cols."""
    cols = [c for c in allowed if c in body]
    if not cols:
        return
    sets = ", ".join(f"{c} = :{c}" for c in cols)
    params = {c: body[c] for c in cols}
    params["__pk"] = pk_val
    db.execute(text(f"UPDATE {table} SET {sets} WHERE {pk_col} = :__pk"), params)


# ─────────────────────────────────────────────────────────────────────────────
# Farms
# ─────────────────────────────────────────────────────────────────────────────

FARM_FIELDS = ["FarmName","ContactName","ContactPhone","ContactEmail","AddressLine",
               "City","Region","Country","HectaresUnder","PrimaryCrops",
               "Certification","Status","JoinedDate","Notes"]


@router.get("/api/aggregator/{business_id}/farms")
def list_farms(business_id: int, status: Optional[str] = None, db: Session = Depends(get_db)):
    where = "WHERE BusinessID = :bid"
    p = {"bid": business_id}
    if status:
        where += " AND Status = :st"; p["st"] = status
    rows = db.execute(text(f"""
        SELECT FarmID, BusinessID, {', '.join(FARM_FIELDS)}, CreatedDate, UpdatedDate
          FROM OFNAggregatorFarm
          {where}
         ORDER BY FarmName
    """), p).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/aggregator/{business_id}/farms")
def create_farm(business_id: int, body: dict, db: Session = Depends(get_db)):
    if not body.get("FarmName"):
        raise HTTPException(400, "FarmName is required")
    res = db.execute(text("""
        INSERT INTO OFNAggregatorFarm
            (BusinessID, FarmName, ContactName, ContactPhone, ContactEmail,
             AddressLine, City, Region, Country, HectaresUnder, PrimaryCrops,
             Certification, Status, JoinedDate, Notes)
        OUTPUT INSERTED.FarmID
        VALUES (:bid, :fn, :cn, :cp, :ce, :addr, :city, :reg, :ctry, :ha, :pc,
                :cert, :st, :jd, :notes)
    """), {
        "bid": business_id,
        "fn":  body["FarmName"],
        "cn":  body.get("ContactName"),
        "cp":  body.get("ContactPhone"),
        "ce":  body.get("ContactEmail"),
        "addr":body.get("AddressLine"),
        "city":body.get("City"),
        "reg": body.get("Region"),
        "ctry":body.get("Country"),
        "ha":  body.get("HectaresUnder"),
        "pc":  body.get("PrimaryCrops"),
        "cert":body.get("Certification"),
        "st":  body.get("Status", "active"),
        "jd":  body.get("JoinedDate"),
        "notes": body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"FarmID": int(res.FarmID)}


@router.put("/api/aggregator/farms/{farm_id}")
def update_farm(farm_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorFarm", "FarmID", farm_id, body, FARM_FIELDS)
    db.execute(text("UPDATE OFNAggregatorFarm SET UpdatedDate = GETDATE() WHERE FarmID = :id"), {"id": farm_id})
    db.commit()
    return {"ok": True}


@router.delete("/api/aggregator/farms/{farm_id}")
def delete_farm(farm_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNAggregatorFarm WHERE FarmID = :id"), {"id": farm_id})
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Contracts
# ─────────────────────────────────────────────────────────────────────────────

CONTRACT_FIELDS = ["FarmID","CropType","ContractType","PricingModel","PricePerKg",
                   "EstimatedKgPerSeason","StartDate","EndDate","ResidueRequirement",
                   "Terms","Status"]


@router.get("/api/aggregator/{business_id}/contracts")
def list_contracts(business_id: int, farm_id: Optional[int] = None, db: Session = Depends(get_db)):
    where = "WHERE c.BusinessID = :bid"
    p = {"bid": business_id}
    if farm_id:
        where += " AND c.FarmID = :fid"; p["fid"] = farm_id
    rows = db.execute(text(f"""
        SELECT c.ContractID, c.BusinessID, c.FarmID, f.FarmName,
               {', '.join('c.'+f for f in CONTRACT_FIELDS if f != 'FarmID')},
               c.CreatedDate
          FROM OFNAggregatorContract c
          LEFT JOIN OFNAggregatorFarm f ON f.FarmID = c.FarmID
          {where}
         ORDER BY c.StartDate DESC, c.ContractID DESC
    """), p).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/aggregator/{business_id}/contracts")
def create_contract(business_id: int, body: dict, db: Session = Depends(get_db)):
    if not body.get("FarmID") or not body.get("CropType"):
        raise HTTPException(400, "FarmID and CropType are required")
    res = db.execute(text("""
        INSERT INTO OFNAggregatorContract
            (BusinessID, FarmID, CropType, ContractType, PricingModel, PricePerKg,
             EstimatedKgPerSeason, StartDate, EndDate, ResidueRequirement, Terms, Status)
        OUTPUT INSERTED.ContractID
        VALUES (:bid, :fid, :ct, :ctype, :pm, :ppk, :ekg, :sd, :ed, :rr, :t, :st)
    """), {
        "bid":  business_id,
        "fid":  int(body["FarmID"]),
        "ct":   body["CropType"],
        "ctype":body.get("ContractType", "first_right"),
        "pm":   body.get("PricingModel", "fixed"),
        "ppk":  body.get("PricePerKg"),
        "ekg":  body.get("EstimatedKgPerSeason"),
        "sd":   body.get("StartDate"),
        "ed":   body.get("EndDate"),
        "rr":   body.get("ResidueRequirement"),
        "t":    body.get("Terms"),
        "st":   body.get("Status", "active"),
    }).fetchone()
    db.commit()
    return {"ContractID": int(res.ContractID)}


@router.put("/api/aggregator/contracts/{contract_id}")
def update_contract(contract_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorContract", "ContractID", contract_id, body, CONTRACT_FIELDS)
    db.commit()
    return {"ok": True}


@router.delete("/api/aggregator/contracts/{contract_id}")
def delete_contract(contract_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNAggregatorContract WHERE ContractID = :id"), {"id": contract_id})
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Inputs (saplings, tunnels, fertilizer)
# ─────────────────────────────────────────────────────────────────────────────

INPUT_FIELDS = ["FarmID","InputType","Description","Quantity","Unit","UnitCost",
                "TotalCost","ProvidedDate","RecoveryModel","Notes"]


@router.get("/api/aggregator/{business_id}/inputs")
def list_inputs(business_id: int, farm_id: Optional[int] = None, db: Session = Depends(get_db)):
    where = "WHERE i.BusinessID = :bid"
    p = {"bid": business_id}
    if farm_id:
        where += " AND i.FarmID = :fid"; p["fid"] = farm_id
    rows = db.execute(text(f"""
        SELECT i.InputID, i.BusinessID, i.FarmID, f.FarmName,
               {', '.join('i.'+f for f in INPUT_FIELDS if f != 'FarmID')},
               i.CreatedDate
          FROM OFNAggregatorInput i
          LEFT JOIN OFNAggregatorFarm f ON f.FarmID = i.FarmID
          {where}
         ORDER BY i.ProvidedDate DESC, i.InputID DESC
    """), p).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/aggregator/{business_id}/inputs")
def create_input(business_id: int, body: dict, db: Session = Depends(get_db)):
    if not body.get("FarmID") or not body.get("InputType"):
        raise HTTPException(400, "FarmID and InputType are required")
    qty  = body.get("Quantity")
    unit = body.get("UnitCost")
    total = body.get("TotalCost")
    if total is None and qty is not None and unit is not None:
        try: total = float(qty) * float(unit)
        except: pass
    res = db.execute(text("""
        INSERT INTO OFNAggregatorInput
            (BusinessID, FarmID, InputType, Description, Quantity, Unit,
             UnitCost, TotalCost, ProvidedDate, RecoveryModel, Notes)
        OUTPUT INSERTED.InputID
        VALUES (:bid, :fid, :it, :d, :q, :u, :uc, :tc, :pd, :rm, :n)
    """), {
        "bid": business_id,
        "fid": int(body["FarmID"]),
        "it":  body["InputType"],
        "d":   body.get("Description"),
        "q":   qty,
        "u":   body.get("Unit"),
        "uc":  unit,
        "tc":  total,
        "pd":  body.get("ProvidedDate"),
        "rm":  body.get("RecoveryModel", "deduct_from_payout"),
        "n":   body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"InputID": int(res.InputID)}


@router.put("/api/aggregator/inputs/{input_id}")
def update_input(input_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorInput", "InputID", input_id, body, INPUT_FIELDS)
    db.commit()
    return {"ok": True}


@router.delete("/api/aggregator/inputs/{input_id}")
def delete_input(input_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNAggregatorInput WHERE InputID = :id"), {"id": input_id})
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Purchases (goods receipts) — also auto-creates an Inventory row
# ─────────────────────────────────────────────────────────────────────────────

PURCHASE_FIELDS = ["FarmID","ContractID","CropType","Grade","QuantityKg","PricePerKg",
                   "TotalPaid","ResidueTestStatus","ResidueTestNotes","HarvestDate",
                   "ReceivedDate","PaymentStatus"]


@router.get("/api/aggregator/{business_id}/purchases")
def list_purchases(business_id: int,
                   farm_id: Optional[int] = None,
                   crop: Optional[str] = None,
                   residue: Optional[str] = None,
                   db: Session = Depends(get_db)):
    where = "WHERE p.BusinessID = :bid"
    pp = {"bid": business_id}
    if farm_id: where += " AND p.FarmID = :fid"; pp["fid"] = farm_id
    if crop:    where += " AND p.CropType = :ct"; pp["ct"] = crop
    if residue: where += " AND p.ResidueTestStatus = :rs"; pp["rs"] = residue
    rows = db.execute(text(f"""
        SELECT p.PurchaseID, p.BusinessID, p.FarmID, f.FarmName, p.ContractID,
               {', '.join('p.'+col for col in PURCHASE_FIELDS if col not in ('FarmID','ContractID'))},
               p.CreatedDate
          FROM OFNAggregatorPurchase p
          LEFT JOIN OFNAggregatorFarm f ON f.FarmID = p.FarmID
          {where}
         ORDER BY p.ReceivedDate DESC, p.PurchaseID DESC
    """), pp).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/aggregator/{business_id}/purchases")
def create_purchase(business_id: int, body: dict, db: Session = Depends(get_db)):
    if not body.get("FarmID") or not body.get("CropType") or not body.get("QuantityKg"):
        raise HTTPException(400, "FarmID, CropType and QuantityKg are required")
    qty = float(body["QuantityKg"])
    ppk = body.get("PricePerKg")
    total = body.get("TotalPaid")
    if total is None and ppk is not None:
        try: total = qty * float(ppk)
        except: pass
    res = db.execute(text("""
        INSERT INTO OFNAggregatorPurchase
            (BusinessID, FarmID, ContractID, CropType, Grade, QuantityKg, PricePerKg,
             TotalPaid, ResidueTestStatus, ResidueTestNotes, HarvestDate, ReceivedDate,
             PaymentStatus)
        OUTPUT INSERTED.PurchaseID
        VALUES (:bid, :fid, :cid, :ct, :g, :q, :ppk, :tp, :rs, :rn, :hd, :rd, :ps)
    """), {
        "bid": business_id,
        "fid": int(body["FarmID"]),
        "cid": body.get("ContractID"),
        "ct":  body["CropType"],
        "g":   body.get("Grade"),
        "q":   qty,
        "ppk": ppk,
        "tp":  total,
        "rs":  body.get("ResidueTestStatus", "pending"),
        "rn":  body.get("ResidueTestNotes"),
        "hd":  body.get("HarvestDate"),
        "rd":  body.get("ReceivedDate"),
        "ps":  body.get("PaymentStatus", "unpaid"),
    }).fetchone()
    purchase_id = int(res.PurchaseID)
    # Auto-create matching inventory row so cold-storage tracking starts immediately
    db.execute(text("""
        INSERT INTO OFNAggregatorInventory
            (BusinessID, PurchaseID, CropType, CurrentKg, ColdStorageUnit,
             TargetTempC, QCStatus)
        VALUES (:bid, :pid, :ct, :q, :csu, :tt, 'ok')
    """), {
        "bid": business_id, "pid": purchase_id,
        "ct":  body["CropType"], "q": qty,
        "csu": body.get("ColdStorageUnit"),
        "tt":  body.get("TargetTempC"),
    })
    db.commit()
    return {"PurchaseID": purchase_id}


@router.put("/api/aggregator/purchases/{purchase_id}")
def update_purchase(purchase_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorPurchase", "PurchaseID", purchase_id, body, PURCHASE_FIELDS)
    db.commit()
    return {"ok": True}


@router.delete("/api/aggregator/purchases/{purchase_id}")
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNAggregatorInventory WHERE PurchaseID = :id"), {"id": purchase_id})
    db.execute(text("DELETE FROM OFNAggregatorPurchase WHERE PurchaseID = :id"), {"id": purchase_id})
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Inventory (cold storage)
# ─────────────────────────────────────────────────────────────────────────────

INVENTORY_FIELDS = ["CropType","CurrentKg","ColdStorageUnit","TargetTempC",
                    "CurrentTempC","QCStatus","ExpiryDate"]


@router.get("/api/aggregator/{business_id}/inventory")
def list_inventory(business_id: int,
                   qc: Optional[str] = None,
                   crop: Optional[str] = None,
                   db: Session = Depends(get_db)):
    where = "WHERE i.BusinessID = :bid"
    p = {"bid": business_id}
    if qc:   where += " AND i.QCStatus = :qc"; p["qc"] = qc
    if crop: where += " AND i.CropType = :ct"; p["ct"] = crop
    rows = db.execute(text(f"""
        SELECT i.InventoryID, i.BusinessID, i.PurchaseID, f.FarmName, i.CropType,
               i.CurrentKg, i.ColdStorageUnit, i.TargetTempC, i.CurrentTempC,
               i.QCStatus, i.ExpiryDate, i.UpdatedDate,
               p.Grade, p.ResidueTestStatus
          FROM OFNAggregatorInventory i
          LEFT JOIN OFNAggregatorPurchase p ON p.PurchaseID = i.PurchaseID
          LEFT JOIN OFNAggregatorFarm f     ON f.FarmID = p.FarmID
          {where}
         ORDER BY i.ExpiryDate, i.InventoryID
    """), p).fetchall()
    return [dict(r._mapping) for r in rows]


@router.put("/api/aggregator/inventory/{inventory_id}")
def update_inventory(inventory_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorInventory", "InventoryID", inventory_id, body, INVENTORY_FIELDS)
    db.execute(text("UPDATE OFNAggregatorInventory SET UpdatedDate = GETDATE() WHERE InventoryID = :id"),
               {"id": inventory_id})
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# B2B accounts + orders
# ─────────────────────────────────────────────────────────────────────────────

B2B_ACCOUNT_FIELDS = ["BuyerName","BuyerType","ContactName","ContactPhone","ContactEmail",
                      "DeliveryAddress","NetTermsDays","CreditLimit","Status","Notes"]
B2B_ORDER_FIELDS = ["AccountID","OrderDate","CropType","QuantityKg","PricePerKg",
                    "TotalValue","DeliveryDate","Status","InvoiceNumber",
                    "PaymentStatus","Notes"]


@router.get("/api/aggregator/{business_id}/b2b/accounts")
def list_b2b_accounts(business_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text(f"""
        SELECT AccountID, BusinessID, {', '.join(B2B_ACCOUNT_FIELDS)}, CreatedDate
          FROM OFNAggregatorB2BAccount
         WHERE BusinessID = :bid
         ORDER BY BuyerName
    """), {"bid": business_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/aggregator/{business_id}/b2b/accounts")
def create_b2b_account(business_id: int, body: dict, db: Session = Depends(get_db)):
    if not body.get("BuyerName"):
        raise HTTPException(400, "BuyerName is required")
    res = db.execute(text("""
        INSERT INTO OFNAggregatorB2BAccount
            (BusinessID, BuyerName, BuyerType, ContactName, ContactPhone, ContactEmail,
             DeliveryAddress, NetTermsDays, CreditLimit, Status, Notes)
        OUTPUT INSERTED.AccountID
        VALUES (:bid, :n, :bt, :cn, :cp, :ce, :da, :nt, :cl, :st, :note)
    """), {
        "bid": business_id,
        "n":   body["BuyerName"],
        "bt":  body.get("BuyerType", "retail"),
        "cn":  body.get("ContactName"),
        "cp":  body.get("ContactPhone"),
        "ce":  body.get("ContactEmail"),
        "da":  body.get("DeliveryAddress"),
        "nt":  body.get("NetTermsDays", 30),
        "cl":  body.get("CreditLimit"),
        "st":  body.get("Status", "active"),
        "note":body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"AccountID": int(res.AccountID)}


@router.put("/api/aggregator/b2b/accounts/{account_id}")
def update_b2b_account(account_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorB2BAccount", "AccountID", account_id, body, B2B_ACCOUNT_FIELDS)
    db.commit()
    return {"ok": True}


@router.delete("/api/aggregator/b2b/accounts/{account_id}")
def delete_b2b_account(account_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNAggregatorB2BAccount WHERE AccountID = :id"), {"id": account_id})
    db.commit()
    return {"ok": True}


@router.get("/api/aggregator/{business_id}/b2b/orders")
def list_b2b_orders(business_id: int, account_id: Optional[int] = None, db: Session = Depends(get_db)):
    where = "WHERE o.BusinessID = :bid"
    p = {"bid": business_id}
    if account_id:
        where += " AND o.AccountID = :aid"; p["aid"] = account_id
    rows = db.execute(text(f"""
        SELECT o.OrderID, o.BusinessID, a.BuyerName,
               {', '.join('o.'+f for f in B2B_ORDER_FIELDS)},
               o.CreatedDate
          FROM OFNAggregatorB2BOrder o
          LEFT JOIN OFNAggregatorB2BAccount a ON a.AccountID = o.AccountID
          {where}
         ORDER BY o.OrderDate DESC, o.OrderID DESC
    """), p).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/aggregator/{business_id}/b2b/orders")
def create_b2b_order(business_id: int, body: dict, db: Session = Depends(get_db)):
    if not body.get("AccountID"):
        raise HTTPException(400, "AccountID is required")
    qty = body.get("QuantityKg")
    ppk = body.get("PricePerKg")
    total = body.get("TotalValue")
    if total is None and qty is not None and ppk is not None:
        try: total = float(qty) * float(ppk)
        except: pass
    res = db.execute(text("""
        INSERT INTO OFNAggregatorB2BOrder
            (BusinessID, AccountID, OrderDate, CropType, QuantityKg, PricePerKg,
             TotalValue, DeliveryDate, Status, InvoiceNumber, PaymentStatus, Notes)
        OUTPUT INSERTED.OrderID
        VALUES (:bid, :aid, :od, :ct, :q, :ppk, :tv, :dd, :st, :inv, :ps, :n)
    """), {
        "bid": business_id,
        "aid": int(body["AccountID"]),
        "od":  body.get("OrderDate"),
        "ct":  body.get("CropType"),
        "q":   qty,
        "ppk": ppk,
        "tv":  total,
        "dd":  body.get("DeliveryDate"),
        "st":  body.get("Status", "placed"),
        "inv": body.get("InvoiceNumber"),
        "ps":  body.get("PaymentStatus", "unpaid"),
        "n":   body.get("Notes"),
    }).fetchone()
    db.commit()
    return {"OrderID": int(res.OrderID)}


@router.put("/api/aggregator/b2b/orders/{order_id}")
def update_b2b_order(order_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorB2BOrder", "OrderID", order_id, body, B2B_ORDER_FIELDS)
    db.commit()
    return {"ok": True}


@router.delete("/api/aggregator/b2b/orders/{order_id}")
def delete_b2b_order(order_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNAggregatorB2BOrder WHERE OrderID = :id"), {"id": order_id})
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# D2C orders (own storefront + delivery-app channels)
# ─────────────────────────────────────────────────────────────────────────────

D2C_FIELDS = ["Channel","ExternalOrderID","CustomerName","CustomerPhone","DeliveryAddress",
              "CropType","QuantityKg","TotalValue","OrderDate","DeliverySLAMinutes","Status"]


@router.get("/api/aggregator/{business_id}/d2c/orders")
def list_d2c_orders(business_id: int, channel: Optional[str] = None, db: Session = Depends(get_db)):
    where = "WHERE BusinessID = :bid"
    p = {"bid": business_id}
    if channel:
        where += " AND Channel = :ch"; p["ch"] = channel
    rows = db.execute(text(f"""
        SELECT OrderID, BusinessID, {', '.join(D2C_FIELDS)}, CreatedDate
          FROM OFNAggregatorD2COrder
          {where}
         ORDER BY OrderDate DESC, OrderID DESC
    """), p).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/aggregator/{business_id}/d2c/orders")
def create_d2c_order(business_id: int, body: dict, db: Session = Depends(get_db)):
    res = db.execute(text("""
        INSERT INTO OFNAggregatorD2COrder
            (BusinessID, Channel, ExternalOrderID, CustomerName, CustomerPhone,
             DeliveryAddress, CropType, QuantityKg, TotalValue, OrderDate,
             DeliverySLAMinutes, Status)
        OUTPUT INSERTED.OrderID
        VALUES (:bid, :ch, :ext, :cn, :cp, :da, :ct, :q, :tv, :od, :sla, :st)
    """), {
        "bid": business_id,
        "ch":  body.get("Channel", "own_app"),
        "ext": body.get("ExternalOrderID"),
        "cn":  body.get("CustomerName"),
        "cp":  body.get("CustomerPhone"),
        "da":  body.get("DeliveryAddress"),
        "ct":  body.get("CropType"),
        "q":   body.get("QuantityKg"),
        "tv":  body.get("TotalValue"),
        "od":  body.get("OrderDate"),
        "sla": body.get("DeliverySLAMinutes"),
        "st":  body.get("Status", "placed"),
    }).fetchone()
    db.commit()
    return {"OrderID": int(res.OrderID)}


@router.put("/api/aggregator/d2c/orders/{order_id}")
def update_d2c_order(order_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorD2COrder", "OrderID", order_id, body, D2C_FIELDS)
    db.commit()
    return {"ok": True}


@router.delete("/api/aggregator/d2c/orders/{order_id}")
def delete_d2c_order(order_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNAggregatorD2COrder WHERE OrderID = :id"), {"id": order_id})
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Logistics / delivery dispatch
# ─────────────────────────────────────────────────────────────────────────────

LOGISTICS_FIELDS = ["OrderType","OrderID","VehicleID","DriverName","DriverPhone",
                    "PickupTime","DeliveryTime","ColdChainTempC","ColdChainBreach",
                    "RouteNotes","Status"]


@router.get("/api/aggregator/{business_id}/logistics")
def list_logistics(business_id: int,
                   status: Optional[str] = None,
                   order_type: Optional[str] = None,
                   db: Session = Depends(get_db)):
    where = "WHERE BusinessID = :bid"
    p = {"bid": business_id}
    if status:     where += " AND Status = :st"; p["st"] = status
    if order_type: where += " AND OrderType = :ot"; p["ot"] = order_type
    rows = db.execute(text(f"""
        SELECT DispatchID, BusinessID, {', '.join(LOGISTICS_FIELDS)}, CreatedDate
          FROM OFNAggregatorLogistics
          {where}
         ORDER BY CreatedDate DESC, DispatchID DESC
    """), p).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/aggregator/{business_id}/logistics")
def create_logistics(business_id: int, body: dict, db: Session = Depends(get_db)):
    if body.get("OrderType") not in ("b2b", "d2c", "inbound"):
        raise HTTPException(400, "OrderType must be b2b / d2c / inbound")
    res = db.execute(text("""
        INSERT INTO OFNAggregatorLogistics
            (BusinessID, OrderType, OrderID, VehicleID, DriverName, DriverPhone,
             PickupTime, DeliveryTime, ColdChainTempC, ColdChainBreach,
             RouteNotes, Status)
        OUTPUT INSERTED.DispatchID
        VALUES (:bid, :ot, :oid, :v, :dn, :dp, :pt, :dt, :ctc, :ccb, :rn, :st)
    """), {
        "bid": business_id,
        "ot":  body["OrderType"],
        "oid": body.get("OrderID"),
        "v":   body.get("VehicleID"),
        "dn":  body.get("DriverName"),
        "dp":  body.get("DriverPhone"),
        "pt":  body.get("PickupTime"),
        "dt":  body.get("DeliveryTime"),
        "ctc": body.get("ColdChainTempC"),
        "ccb": 1 if body.get("ColdChainBreach") else 0,
        "rn":  body.get("RouteNotes"),
        "st":  body.get("Status", "scheduled"),
    }).fetchone()
    db.commit()
    return {"DispatchID": int(res.DispatchID)}


@router.put("/api/aggregator/logistics/{dispatch_id}")
def update_logistics(dispatch_id: int, body: dict, db: Session = Depends(get_db)):
    _update_row(db, "OFNAggregatorLogistics", "DispatchID", dispatch_id, body, LOGISTICS_FIELDS)
    db.commit()
    return {"ok": True}


@router.delete("/api/aggregator/logistics/{dispatch_id}")
def delete_logistics(dispatch_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNAggregatorLogistics WHERE DispatchID = :id"), {"id": dispatch_id})
    db.commit()
    return {"ok": True}
