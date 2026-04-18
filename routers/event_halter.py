"""
Halter Show (full livestock show).

Modernized replacement for the classic ASP EventHalter.asp, HalterClassList.asp,
EventAddAnimal.asp, and judging pages. Admin configures the show, defines classes
(per breed/gender/age), accepts animal registrations, assigns pens, and awards
placements. Attendees register their animals from the Animals table, pick classes,
reserve pens, and add extras (vet check, electricity, stall mats).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, SessionLocal
from datetime import date

router = APIRouter()


def ensure_tables(db: Session):
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventHalterConfig')
        CREATE TABLE OFNEventHalterConfig (
            ConfigID                INT IDENTITY(1,1) PRIMARY KEY,
            EventID                 INT NOT NULL UNIQUE,
            Description             NVARCHAR(MAX),
            FeePerAnimal            DECIMAL(10,2) DEFAULT 0,
            DiscountFeePerAnimal    DECIMAL(10,2),
            DiscountEndDate         DATE,
            FeePerPen               DECIMAL(10,2) DEFAULT 0,
            FeePerProductionAnimal  DECIMAL(10,2) DEFAULT 0,
            VetCheckFee             DECIMAL(10,2) DEFAULT 0,
            ElectricityFee          DECIMAL(10,2) DEFAULT 0,
            StallMatFee             DECIMAL(10,2) DEFAULT 0,
            MaxPensPerFarm          INT,
            MaxJuvenilesPerPen      INT,
            MaxAdultsPerPen         INT,
            RegistrationEndDate     DATE,
            IsActive                BIT DEFAULT 1,
            CreatedDate             DATETIME DEFAULT GETDATE(),
            UpdatedDate             DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventHalterClasses')
        CREATE TABLE OFNEventHalterClasses (
            ClassID        INT IDENTITY(1,1) PRIMARY KEY,
            EventID        INT NOT NULL,
            ClassName      NVARCHAR(200) NOT NULL,
            ClassCode      NVARCHAR(50),
            ShornCode      NVARCHAR(50),
            Breed          NVARCHAR(100),
            Gender         NVARCHAR(50),
            AgeGroup       NVARCHAR(100),
            ClassType      NVARCHAR(50) DEFAULT 'Halter',
            DisplayOrder   INT DEFAULT 0,
            IsActive       BIT DEFAULT 1
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventHalterRegistrations')
        CREATE TABLE OFNEventHalterRegistrations (
            RegID              INT IDENTITY(1,1) PRIMARY KEY,
            EventID            INT NOT NULL,
            PeopleID           INT NOT NULL,
            BusinessID         INT,
            AnimalID           INT NOT NULL,
            RegistrationType   NVARCHAR(50) DEFAULT 'Halter',
            IsShorn            BIT DEFAULT 0,
            IsCheckedIn        BIT DEFAULT 0,
            CheckInNotes       NVARCHAR(MAX),
            PaidStatus         NVARCHAR(20) DEFAULT 'pending',
            Fee                DECIMAL(10,2) DEFAULT 0,
            CreatedDate        DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventHalterClassEntries')
        CREATE TABLE OFNEventHalterClassEntries (
            EntryID      INT IDENTITY(1,1) PRIMARY KEY,
            RegID        INT NOT NULL,
            ClassID      INT NOT NULL,
            Placement    NVARCHAR(50),
            JudgeNotes   NVARCHAR(MAX),
            ScoresheetJSON NVARCHAR(MAX),
            CreatedDate  DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventHalterPens')
        CREATE TABLE OFNEventHalterPens (
            PenID            INT IDENTITY(1,1) PRIMARY KEY,
            EventID          INT NOT NULL,
            PeopleID         INT NOT NULL,
            BusinessID       INT,
            PenNumber        INT,
            PenType          NVARCHAR(50),
            NeedsElectricity BIT DEFAULT 0,
            NeedsStallMat    BIT DEFAULT 0,
            NeedsVetCheck    BIT DEFAULT 0,
            Notes            NVARCHAR(MAX),
            Fee              DECIMAL(10,2) DEFAULT 0,
            CreatedDate      DATETIME DEFAULT GETDATE()
        )
    """))
    db.commit()


try:
    with SessionLocal() as _db:
        ensure_tables(_db)
except Exception as e:
    print(f"[event_halter] Table ensure warning: {e}")


def _current_animal_fee(cfg: dict) -> float:
    full = float(cfg.get("FeePerAnimal") or 0)
    disc = cfg.get("DiscountFeePerAnimal")
    end = cfg.get("DiscountEndDate")
    if disc is not None and end:
        try:
            if end >= date.today():
                return float(disc)
        except Exception:
            pass
    return full


# ---------- CONFIG ----------

@router.get("/api/events/{event_id}/halter/config")
def get_halter_config(event_id: int, db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT * FROM OFNEventHalterConfig WHERE EventID = :eid
    """), {"eid": event_id}).fetchone()
    if not row:
        return {"configured": False, "EventID": event_id}
    cfg = dict(row._mapping)
    cfg["configured"] = True
    cfg["CurrentFeePerAnimal"] = _current_animal_fee(cfg)
    return cfg


@router.put("/api/events/{event_id}/halter/config")
def put_halter_config(event_id: int, body: dict, db: Session = Depends(get_db)):
    exists = db.execute(text("SELECT ConfigID FROM OFNEventHalterConfig WHERE EventID = :eid"),
                       {"eid": event_id}).fetchone()
    params = {
        "eid": event_id,
        "desc": body.get("Description"),
        "fee": body.get("FeePerAnimal") or 0,
        "dfee": body.get("DiscountFeePerAnimal"),
        "dend": body.get("DiscountEndDate"),
        "fpen": body.get("FeePerPen") or 0,
        "fprod": body.get("FeePerProductionAnimal") or 0,
        "vet": body.get("VetCheckFee") or 0,
        "elec": body.get("ElectricityFee") or 0,
        "mat": body.get("StallMatFee") or 0,
        "mpens": body.get("MaxPensPerFarm"),
        "mjuv": body.get("MaxJuvenilesPerPen"),
        "madu": body.get("MaxAdultsPerPen"),
        "rend": body.get("RegistrationEndDate"),
        "active": 1 if body.get("IsActive", True) else 0,
    }
    if exists:
        db.execute(text("""
            UPDATE OFNEventHalterConfig SET
              Description=:desc, FeePerAnimal=:fee, DiscountFeePerAnimal=:dfee,
              DiscountEndDate=:dend, FeePerPen=:fpen, FeePerProductionAnimal=:fprod,
              VetCheckFee=:vet, ElectricityFee=:elec, StallMatFee=:mat,
              MaxPensPerFarm=:mpens, MaxJuvenilesPerPen=:mjuv, MaxAdultsPerPen=:madu,
              RegistrationEndDate=:rend, IsActive=:active, UpdatedDate=GETDATE()
            WHERE EventID=:eid
        """), params)
    else:
        db.execute(text("""
            INSERT INTO OFNEventHalterConfig
              (EventID, Description, FeePerAnimal, DiscountFeePerAnimal, DiscountEndDate,
               FeePerPen, FeePerProductionAnimal, VetCheckFee, ElectricityFee, StallMatFee,
               MaxPensPerFarm, MaxJuvenilesPerPen, MaxAdultsPerPen, RegistrationEndDate, IsActive)
            VALUES (:eid, :desc, :fee, :dfee, :dend, :fpen, :fprod, :vet, :elec, :mat,
                    :mpens, :mjuv, :madu, :rend, :active)
        """), params)
    db.commit()
    return {"ok": True}


# ---------- CLASSES ----------

@router.get("/api/events/{event_id}/halter/classes")
def list_classes(event_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT * FROM OFNEventHalterClasses
        WHERE EventID = :eid AND IsActive = 1
        ORDER BY Breed, DisplayOrder, ClassName
    """), {"eid": event_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/events/{event_id}/halter/classes")
def add_class(event_id: int, body: dict, db: Session = Depends(get_db)):
    r = db.execute(text("""
        INSERT INTO OFNEventHalterClasses
          (EventID, ClassName, ClassCode, ShornCode, Breed, Gender, AgeGroup, ClassType, DisplayOrder)
        VALUES (:eid, :n, :c, :sc, :b, :g, :a, :t, :o);
        SELECT SCOPE_IDENTITY() AS NewID;
    """), {
        "eid": event_id,
        "n": body.get("ClassName"),
        "c": body.get("ClassCode"),
        "sc": body.get("ShornCode"),
        "b": body.get("Breed"),
        "g": body.get("Gender"),
        "a": body.get("AgeGroup"),
        "t": body.get("ClassType") or "Halter",
        "o": body.get("DisplayOrder") or 0,
    })
    new_id = r.fetchone()[0]
    db.commit()
    return {"ClassID": int(new_id)}


@router.put("/api/events/halter/classes/{class_id}")
def edit_class(class_id: int, body: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OFNEventHalterClasses SET
          ClassName=:n, ClassCode=:c, ShornCode=:sc, Breed=:b,
          Gender=:g, AgeGroup=:a, ClassType=:t, DisplayOrder=:o
        WHERE ClassID=:cid
    """), {
        "cid": class_id,
        "n": body.get("ClassName"),
        "c": body.get("ClassCode"),
        "sc": body.get("ShornCode"),
        "b": body.get("Breed"),
        "g": body.get("Gender"),
        "a": body.get("AgeGroup"),
        "t": body.get("ClassType") or "Halter",
        "o": body.get("DisplayOrder") or 0,
    })
    db.commit()
    return {"ok": True}


@router.delete("/api/events/halter/classes/{class_id}")
def delete_class(class_id: int, db: Session = Depends(get_db)):
    db.execute(text("UPDATE OFNEventHalterClasses SET IsActive=0 WHERE ClassID=:cid"),
               {"cid": class_id})
    db.commit()
    return {"ok": True}


@router.post("/api/events/{event_id}/halter/classes/bulk-seed")
def bulk_seed_classes(event_id: int, body: dict, db: Session = Depends(get_db)):
    """Seed a standard alpaca halter class set for a breed."""
    breed = body.get("Breed") or "Huacaya"
    template = body.get("Template") or "alpaca-standard"
    if template != "alpaca-standard":
        raise HTTPException(400, "unknown template")
    existing = db.execute(text("""
        SELECT COUNT(*) FROM OFNEventHalterClasses WHERE EventID=:eid AND Breed=:b AND IsActive=1
    """), {"eid": event_id, "b": breed}).fetchone()[0]
    if existing:
        raise HTTPException(400, f"{breed} classes already exist for this event")
    colors = ["White", "Beige", "Light Fawn", "Medium Fawn", "Dark Fawn",
              "Light Brown", "Medium Brown", "Dark Brown", "Bay Black", "True Black",
              "Light Silver Grey", "Medium Silver Grey", "Dark Silver Grey",
              "Light Rose Grey", "Medium Rose Grey", "Dark Rose Grey", "Multi"]
    ages = [("Juvenile", "6-12 months"), ("Yearling", "12-24 months"),
            ("Two Year Old", "24-36 months"), ("Adult", "36+ months")]
    order = 0
    for color in colors:
        for age_name, age_desc in ages:
            for gender in ("Female", "Male"):
                order += 1
                name = f"{color} {age_name} {gender}"
                code = f"{breed[:1]}-{color[:2].upper()}-{age_name[:1]}{gender[:1]}"
                db.execute(text("""
                    INSERT INTO OFNEventHalterClasses
                      (EventID, ClassName, ClassCode, Breed, Gender, AgeGroup, ClassType, DisplayOrder)
                    VALUES (:eid, :n, :c, :b, :g, :a, 'Halter', :o)
                """), {"eid": event_id, "n": name, "c": code, "b": breed,
                       "g": gender, "a": age_desc, "o": order})
    db.commit()
    return {"ok": True, "count": order}


# ---------- REGISTRATIONS ----------

@router.get("/api/events/{event_id}/halter/registrations")
def list_registrations(event_id: int, people_id: int | None = None, db: Session = Depends(get_db)):
    filt = "WHERE r.EventID = :eid"
    params = {"eid": event_id}
    if people_id:
        filt += " AND r.PeopleID = :pid"
        params["pid"] = people_id
    rows = db.execute(text(f"""
        SELECT r.*,
               a.AnimalName, a.DateOfBirth, a.Gender AS AnimalGender,
               a.FleeceColorID, a.RegisteredName,
               p.FirstName, p.LastName,
               b.BusinessName
        FROM OFNEventHalterRegistrations r
        LEFT JOIN Animals a ON a.AnimalID = r.AnimalID
        LEFT JOIN People p ON p.PeopleID = r.PeopleID
        LEFT JOIN Business b ON b.BusinessID = r.BusinessID
        {filt}
        ORDER BY r.CreatedDate DESC
    """), params).fetchall()
    regs = [dict(r._mapping) for r in rows]
    if regs:
        reg_ids = [r["RegID"] for r in regs]
        placeholders = ",".join(f":id{i}" for i, _ in enumerate(reg_ids))
        ep = {f"id{i}": rid for i, rid in enumerate(reg_ids)}
        entry_rows = db.execute(text(f"""
            SELECT e.*, c.ClassName, c.ClassCode, c.Breed, c.Gender, c.AgeGroup
            FROM OFNEventHalterClassEntries e
            LEFT JOIN OFNEventHalterClasses c ON c.ClassID = e.ClassID
            WHERE e.RegID IN ({placeholders})
        """), ep).fetchall()
        by_reg = {}
        for e in entry_rows:
            d = dict(e._mapping)
            by_reg.setdefault(d["RegID"], []).append(d)
        for r in regs:
            r["classes"] = by_reg.get(r["RegID"], [])
    return regs


@router.post("/api/events/{event_id}/halter/registrations")
def add_registration(event_id: int, body: dict, db: Session = Depends(get_db)):
    cfg_row = db.execute(text("SELECT * FROM OFNEventHalterConfig WHERE EventID=:eid"),
                        {"eid": event_id}).fetchone()
    if not cfg_row:
        raise HTTPException(400, "Show is not configured")
    cfg = dict(cfg_row._mapping)
    if cfg.get("RegistrationEndDate") and cfg["RegistrationEndDate"] < date.today():
        raise HTTPException(400, "Registration has closed")
    if not body.get("PeopleID") or not body.get("AnimalID"):
        raise HTTPException(400, "PeopleID and AnimalID required")
    reg_type = body.get("RegistrationType") or "Halter"
    if reg_type == "Production":
        fee = float(cfg.get("FeePerProductionAnimal") or 0)
    else:
        fee = _current_animal_fee(cfg)
    r = db.execute(text("""
        INSERT INTO OFNEventHalterRegistrations
          (EventID, PeopleID, BusinessID, AnimalID, RegistrationType, IsShorn, Fee)
        VALUES (:eid, :pid, :bid, :aid, :rt, :shorn, :fee);
        SELECT SCOPE_IDENTITY() AS NewID;
    """), {
        "eid": event_id,
        "pid": body.get("PeopleID"),
        "bid": body.get("BusinessID"),
        "aid": body.get("AnimalID"),
        "rt": reg_type,
        "shorn": 1 if body.get("IsShorn") else 0,
        "fee": fee,
    })
    reg_id = int(r.fetchone()[0])
    for cid in body.get("ClassIDs") or []:
        db.execute(text("""
            INSERT INTO OFNEventHalterClassEntries (RegID, ClassID) VALUES (:r, :c)
        """), {"r": reg_id, "c": int(cid)})
    db.commit()
    return {"RegID": reg_id, "Fee": fee}


@router.put("/api/events/halter/registrations/{reg_id}")
def update_registration(reg_id: int, body: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OFNEventHalterRegistrations SET
          IsShorn=:shorn, IsCheckedIn=:chk, CheckInNotes=:notes, PaidStatus=:paid
        WHERE RegID=:rid
    """), {
        "rid": reg_id,
        "shorn": 1 if body.get("IsShorn") else 0,
        "chk": 1 if body.get("IsCheckedIn") else 0,
        "notes": body.get("CheckInNotes"),
        "paid": body.get("PaidStatus") or "pending",
    })
    if "ClassIDs" in body:
        db.execute(text("DELETE FROM OFNEventHalterClassEntries WHERE RegID=:r"),
                  {"r": reg_id})
        for cid in body.get("ClassIDs") or []:
            db.execute(text("""
                INSERT INTO OFNEventHalterClassEntries (RegID, ClassID) VALUES (:r, :c)
            """), {"r": reg_id, "c": int(cid)})
    db.commit()
    return {"ok": True}


@router.delete("/api/events/halter/registrations/{reg_id}")
def delete_registration(reg_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNEventHalterClassEntries WHERE RegID=:r"), {"r": reg_id})
    db.execute(text("DELETE FROM OFNEventHalterRegistrations WHERE RegID=:r"), {"r": reg_id})
    db.commit()
    return {"ok": True}


# ---------- JUDGING ----------

@router.get("/api/events/{event_id}/halter/classes/{class_id}/entries")
def class_entries(event_id: int, class_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT e.*, r.AnimalID, r.PeopleID, r.BusinessID, r.IsShorn, r.IsCheckedIn,
               a.AnimalName, a.RegisteredName, a.DateOfBirth,
               b.BusinessName, p.FirstName, p.LastName
        FROM OFNEventHalterClassEntries e
        JOIN OFNEventHalterRegistrations r ON r.RegID = e.RegID
        LEFT JOIN Animals a ON a.AnimalID = r.AnimalID
        LEFT JOIN People p ON p.PeopleID = r.PeopleID
        LEFT JOIN Business b ON b.BusinessID = r.BusinessID
        WHERE r.EventID = :eid AND e.ClassID = :cid
        ORDER BY e.Placement, a.AnimalName
    """), {"eid": event_id, "cid": class_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.put("/api/events/halter/entries/{entry_id}/judge")
def judge_entry(entry_id: int, body: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OFNEventHalterClassEntries SET
          Placement=:p, JudgeNotes=:n, ScoresheetJSON=:s
        WHERE EntryID=:eid
    """), {
        "eid": entry_id,
        "p": body.get("Placement"),
        "n": body.get("JudgeNotes"),
        "s": body.get("ScoresheetJSON"),
    })
    db.commit()
    return {"ok": True}


# ---------- PENS ----------

@router.get("/api/events/{event_id}/halter/pens")
def list_pens(event_id: int, people_id: int | None = None, db: Session = Depends(get_db)):
    filt = "WHERE p.EventID = :eid"
    params = {"eid": event_id}
    if people_id:
        filt += " AND p.PeopleID = :pid"
        params["pid"] = people_id
    rows = db.execute(text(f"""
        SELECT p.*, b.BusinessName, pe.FirstName, pe.LastName
        FROM OFNEventHalterPens p
        LEFT JOIN Business b ON b.BusinessID = p.BusinessID
        LEFT JOIN People pe ON pe.PeopleID = p.PeopleID
        {filt}
        ORDER BY p.PenNumber, p.CreatedDate
    """), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/api/events/{event_id}/halter/pens")
def add_pen(event_id: int, body: dict, db: Session = Depends(get_db)):
    cfg_row = db.execute(text("SELECT * FROM OFNEventHalterConfig WHERE EventID=:eid"),
                        {"eid": event_id}).fetchone()
    cfg = dict(cfg_row._mapping) if cfg_row else {}
    fee = float(cfg.get("FeePerPen") or 0)
    if body.get("NeedsElectricity"):
        fee += float(cfg.get("ElectricityFee") or 0)
    if body.get("NeedsStallMat"):
        fee += float(cfg.get("StallMatFee") or 0)
    if body.get("NeedsVetCheck"):
        fee += float(cfg.get("VetCheckFee") or 0)
    r = db.execute(text("""
        INSERT INTO OFNEventHalterPens
          (EventID, PeopleID, BusinessID, PenType, NeedsElectricity, NeedsStallMat, NeedsVetCheck, Notes, Fee)
        VALUES (:eid, :pid, :bid, :t, :e, :m, :v, :n, :f);
        SELECT SCOPE_IDENTITY() AS NewID;
    """), {
        "eid": event_id,
        "pid": body.get("PeopleID"),
        "bid": body.get("BusinessID"),
        "t": body.get("PenType") or "Adult",
        "e": 1 if body.get("NeedsElectricity") else 0,
        "m": 1 if body.get("NeedsStallMat") else 0,
        "v": 1 if body.get("NeedsVetCheck") else 0,
        "n": body.get("Notes"),
        "f": fee,
    })
    pen_id = int(r.fetchone()[0])
    db.commit()
    return {"PenID": pen_id, "Fee": fee}


@router.delete("/api/events/halter/pens/{pen_id}")
def delete_pen(pen_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNEventHalterPens WHERE PenID=:p"), {"p": pen_id})
    db.commit()
    return {"ok": True}
