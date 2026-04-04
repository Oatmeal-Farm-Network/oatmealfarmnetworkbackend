from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter()

# ── Auto-create tables on startup ─────────────────────────────────────────────
def ensure_tables(db: Session):
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEvents')
        CREATE TABLE OFNEvents (
            EventID         INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID      INT NOT NULL,
            PeopleID        INT,
            EventName       NVARCHAR(200) NOT NULL,
            EventDescription NVARCHAR(MAX),
            EventType       NVARCHAR(100),
            EventStartDate  DATE,
            EventEndDate    DATE,
            EventImage      NVARCHAR(500),
            EventLocationName NVARCHAR(200),
            EventLocationStreet NVARCHAR(200),
            EventLocationCity   NVARCHAR(100),
            EventLocationState  NVARCHAR(100),
            EventLocationZip    NVARCHAR(20),
            EventContactEmail   NVARCHAR(200),
            EventPhone          NVARCHAR(50),
            EventWebsite        NVARCHAR(500),
            IsPublished         BIT DEFAULT 1,
            IsFree              BIT DEFAULT 1,
            RegistrationRequired BIT DEFAULT 0,
            MaxAttendees        INT,
            Deleted             BIT DEFAULT 0,
            CreatedDate         DATETIME DEFAULT GETDATE()
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventDates')
        CREATE TABLE OFNEventDates (
            DateID      INT IDENTITY(1,1) PRIMARY KEY,
            EventID     INT NOT NULL,
            EventDate   DATE NOT NULL,
            StartTime   NVARCHAR(10),
            EndTime     NVARCHAR(10)
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventOptions')
        CREATE TABLE OFNEventOptions (
            OptionID    INT IDENTITY(1,1) PRIMARY KEY,
            EventID     INT NOT NULL,
            OptionName  NVARCHAR(200) NOT NULL,
            OptionDescription NVARCHAR(MAX),
            Price       DECIMAL(10,2) DEFAULT 0,
            MaxQty      INT,
            IsActive    BIT DEFAULT 1
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventRegistrations')
        CREATE TABLE OFNEventRegistrations (
            RegID               INT IDENTITY(1,1) PRIMARY KEY,
            EventID             INT NOT NULL,
            PeopleID            INT,
            BusinessID          INT,
            RegDate             DATETIME DEFAULT GETDATE(),
            TotalAmount         DECIMAL(10,2) DEFAULT 0,
            PaymentStatus       NVARCHAR(50) DEFAULT 'pending',
            AttendeeFirstName   NVARCHAR(100),
            AttendeeLastName    NVARCHAR(100),
            AttendeeEmail       NVARCHAR(200),
            AttendeePhone       NVARCHAR(50),
            Notes               NVARCHAR(MAX)
        )
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'OFNEventRegistrationItems')
        CREATE TABLE OFNEventRegistrationItems (
            ItemID      INT IDENTITY(1,1) PRIMARY KEY,
            RegID       INT NOT NULL,
            OptionID    INT,
            OptionName  NVARCHAR(200),
            Quantity    INT DEFAULT 1,
            UnitPrice   DECIMAL(10,2) DEFAULT 0
        )
    """))
    db.commit()

with __import__('database').SessionLocal() as _db:
    try:
        ensure_tables(_db)
    except Exception as e:
        print(f"Events table setup error: {e}")


# ── Public: list upcoming events ──────────────────────────────────────────────
@router.get("/api/events")
def list_events(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT e.EventID, e.BusinessID, b.BusinessName, e.EventName, e.EventDescription,
               e.EventType, e.EventStartDate, e.EventEndDate, e.EventImage,
               e.EventLocationName, e.EventLocationCity, e.EventLocationState,
               e.EventContactEmail, e.EventPhone, e.EventWebsite,
               e.IsFree, e.RegistrationRequired, e.MaxAttendees,
               (SELECT COUNT(1) FROM OFNEventRegistrations r WHERE r.EventID = e.EventID) AS AttendeeCount
        FROM OFNEvents e
        JOIN Business b ON e.BusinessID = b.BusinessID
        WHERE e.Deleted = 0 AND e.IsPublished = 1
          AND (e.EventEndDate IS NULL OR e.EventEndDate >= CAST(GETDATE() AS DATE))
        ORDER BY e.EventStartDate ASC
    """)).fetchall()
    return [dict(r._mapping) for r in rows]


# ── Public: single event detail ───────────────────────────────────────────────
@router.get("/api/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT e.*, b.BusinessName,
               (SELECT COUNT(1) FROM OFNEventRegistrations r WHERE r.EventID = e.EventID) AS AttendeeCount
        FROM OFNEvents e
        JOIN Business b ON e.BusinessID = b.BusinessID
        WHERE e.EventID = :eid AND e.Deleted = 0
    """), {"eid": event_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    d = dict(row._mapping)

    # Dates
    dates = db.execute(text("""
        SELECT * FROM OFNEventDates WHERE EventID = :eid ORDER BY EventDate
    """), {"eid": event_id}).fetchall()
    d["dates"] = [dict(r._mapping) for r in dates]

    # Options
    opts = db.execute(text("""
        SELECT * FROM OFNEventOptions WHERE EventID = :eid AND IsActive = 1 ORDER BY OptionID
    """), {"eid": event_id}).fetchall()
    d["options"] = [dict(r._mapping) for r in opts]

    return d


# ── Account: list my events (as organizer) ────────────────────────────────────
@router.get("/api/events/my-events")
def my_events(business_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT e.EventID, e.EventName, e.EventStartDate, e.EventEndDate,
               e.EventType, e.EventLocationCity, e.EventLocationState,
               e.IsPublished, e.IsFree, e.RegistrationRequired,
               (SELECT COUNT(1) FROM OFNEventRegistrations r WHERE r.EventID = e.EventID) AS AttendeeCount
        FROM OFNEvents e
        WHERE e.BusinessID = :bid AND e.Deleted = 0
        ORDER BY e.EventStartDate DESC
    """), {"bid": business_id}).fetchall()
    return [dict(r._mapping) for r in rows]


# ── Create event ──────────────────────────────────────────────────────────────
@router.post("/api/events")
def create_event(data: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO OFNEvents (BusinessID, PeopleID, EventName, EventDescription, EventType,
            EventStartDate, EventEndDate, EventImage, EventLocationName, EventLocationStreet,
            EventLocationCity, EventLocationState, EventLocationZip,
            EventContactEmail, EventPhone, EventWebsite,
            IsPublished, IsFree, RegistrationRequired, MaxAttendees)
        VALUES (:bid, :pid, :name, :desc, :type,
            :start, :end, :img, :locname, :street,
            :city, :state, :zip,
            :email, :phone, :web,
            :pub, :free, :reqreg, :max)
    """), {
        "bid":    data.get("BusinessID"),
        "pid":    data.get("PeopleID") or None,
        "name":   data.get("EventName"),
        "desc":   data.get("EventDescription") or None,
        "type":   data.get("EventType") or None,
        "start":  data.get("EventStartDate") or None,
        "end":    data.get("EventEndDate") or None,
        "img":    data.get("EventImage") or None,
        "locname": data.get("EventLocationName") or None,
        "street": data.get("EventLocationStreet") or None,
        "city":   data.get("EventLocationCity") or None,
        "state":  data.get("EventLocationState") or None,
        "zip":    data.get("EventLocationZip") or None,
        "email":  data.get("EventContactEmail") or None,
        "phone":  data.get("EventPhone") or None,
        "web":    data.get("EventWebsite") or None,
        "pub":    data.get("IsPublished", 1),
        "free":   data.get("IsFree", 1),
        "reqreg": data.get("RegistrationRequired", 0),
        "max":    data.get("MaxAttendees") or None,
    })
    new_id = db.execute(text("SELECT SCOPE_IDENTITY() AS id")).fetchone()
    db.commit()
    return {"EventID": int(new_id.id)}


# ── Update event ──────────────────────────────────────────────────────────────
@router.put("/api/events/{event_id}")
def update_event(event_id: int, data: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OFNEvents SET
            EventName            = :name,
            EventDescription     = :desc,
            EventType            = :type,
            EventStartDate       = :start,
            EventEndDate         = :end,
            EventImage           = :img,
            EventLocationName    = :locname,
            EventLocationStreet  = :street,
            EventLocationCity    = :city,
            EventLocationState   = :state,
            EventLocationZip     = :zip,
            EventContactEmail    = :email,
            EventPhone           = :phone,
            EventWebsite         = :web,
            IsPublished          = :pub,
            IsFree               = :free,
            RegistrationRequired = :reqreg,
            MaxAttendees         = :max
        WHERE EventID = :eid
    """), {
        "eid":    event_id,
        "name":   data.get("EventName"),
        "desc":   data.get("EventDescription") or None,
        "type":   data.get("EventType") or None,
        "start":  data.get("EventStartDate") or None,
        "end":    data.get("EventEndDate") or None,
        "img":    data.get("EventImage") or None,
        "locname": data.get("EventLocationName") or None,
        "street": data.get("EventLocationStreet") or None,
        "city":   data.get("EventLocationCity") or None,
        "state":  data.get("EventLocationState") or None,
        "zip":    data.get("EventLocationZip") or None,
        "email":  data.get("EventContactEmail") or None,
        "phone":  data.get("EventPhone") or None,
        "web":    data.get("EventWebsite") or None,
        "pub":    data.get("IsPublished", 1),
        "free":   data.get("IsFree", 1),
        "reqreg": data.get("RegistrationRequired", 0),
        "max":    data.get("MaxAttendees") or None,
    })
    db.commit()
    return {"ok": True}


# ── Delete event (soft) ───────────────────────────────────────────────────────
@router.delete("/api/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    db.execute(text("UPDATE OFNEvents SET Deleted = 1 WHERE EventID = :eid"), {"eid": event_id})
    db.commit()
    return {"ok": True}


# ── Event dates ───────────────────────────────────────────────────────────────
@router.get("/api/events/{event_id}/dates")
def get_dates(event_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM OFNEventDates WHERE EventID = :eid ORDER BY EventDate"), {"eid": event_id}).fetchall()
    return [dict(r._mapping) for r in rows]

@router.post("/api/events/{event_id}/dates")
def add_date(event_id: int, data: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO OFNEventDates (EventID, EventDate, StartTime, EndTime)
        VALUES (:eid, :dt, :st, :et)
    """), {"eid": event_id, "dt": data.get("EventDate"), "st": data.get("StartTime") or None, "et": data.get("EndTime") or None})
    new_id = db.execute(text("SELECT SCOPE_IDENTITY() AS id")).fetchone()
    db.commit()
    return {"DateID": int(new_id.id)}

@router.delete("/api/events/dates/{date_id}")
def delete_date(date_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNEventDates WHERE DateID = :did"), {"did": date_id})
    db.commit()
    return {"ok": True}


# ── Event options (registration items) ───────────────────────────────────────
@router.get("/api/events/{event_id}/options")
def get_options(event_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM OFNEventOptions WHERE EventID = :eid ORDER BY OptionID"), {"eid": event_id}).fetchall()
    return [dict(r._mapping) for r in rows]

@router.post("/api/events/{event_id}/options")
def add_option(event_id: int, data: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO OFNEventOptions (EventID, OptionName, OptionDescription, Price, MaxQty, IsActive)
        VALUES (:eid, :name, :desc, :price, :max, 1)
    """), {
        "eid":   event_id,
        "name":  data.get("OptionName"),
        "desc":  data.get("OptionDescription") or None,
        "price": data.get("Price", 0),
        "max":   data.get("MaxQty") or None,
    })
    new_id = db.execute(text("SELECT SCOPE_IDENTITY() AS id")).fetchone()
    db.commit()
    return {"OptionID": int(new_id.id)}

@router.put("/api/events/options/{option_id}")
def update_option(option_id: int, data: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OFNEventOptions SET
            OptionName = :name, OptionDescription = :desc,
            Price = :price, MaxQty = :max, IsActive = :active
        WHERE OptionID = :oid
    """), {
        "oid":   option_id,
        "name":  data.get("OptionName"),
        "desc":  data.get("OptionDescription") or None,
        "price": data.get("Price", 0),
        "max":   data.get("MaxQty") or None,
        "active": data.get("IsActive", 1),
    })
    db.commit()
    return {"ok": True}

@router.delete("/api/events/options/{option_id}")
def delete_option(option_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM OFNEventOptions WHERE OptionID = :oid"), {"oid": option_id})
    db.commit()
    return {"ok": True}


# ── Register for event ────────────────────────────────────────────────────────
@router.post("/api/events/{event_id}/register")
def register(event_id: int, data: dict, db: Session = Depends(get_db)):
    items = data.get("items", [])
    total = sum(float(i.get("UnitPrice", 0)) * int(i.get("Quantity", 1)) for i in items)

    db.execute(text("""
        INSERT INTO OFNEventRegistrations
            (EventID, PeopleID, BusinessID, TotalAmount, PaymentStatus,
             AttendeeFirstName, AttendeeLastName, AttendeeEmail, AttendeePhone, Notes)
        VALUES
            (:eid, :pid, :bid, :total, 'pending',
             :first, :last, :email, :phone, :notes)
    """), {
        "eid":   event_id,
        "pid":   data.get("PeopleID") or None,
        "bid":   data.get("BusinessID") or None,
        "total": total,
        "first": data.get("AttendeeFirstName"),
        "last":  data.get("AttendeeLastName"),
        "email": data.get("AttendeeEmail"),
        "phone": data.get("AttendeePhone") or None,
        "notes": data.get("Notes") or None,
    })
    reg_id = db.execute(text("SELECT SCOPE_IDENTITY() AS id")).fetchone()
    reg_id = int(reg_id.id)

    for item in items:
        if item.get("Quantity", 0) > 0:
            db.execute(text("""
                INSERT INTO OFNEventRegistrationItems (RegID, OptionID, OptionName, Quantity, UnitPrice)
                VALUES (:rid, :oid, :name, :qty, :price)
            """), {
                "rid":   reg_id,
                "oid":   item.get("OptionID") or None,
                "name":  item.get("OptionName"),
                "qty":   item.get("Quantity", 1),
                "price": item.get("UnitPrice", 0),
            })

    db.commit()
    return {"RegID": reg_id, "TotalAmount": total}


# ── My registrations ──────────────────────────────────────────────────────────
@router.get("/api/events/my-registrations")
def my_registrations(people_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT r.RegID, r.EventID, r.RegDate, r.TotalAmount, r.PaymentStatus,
               e.EventName, e.EventStartDate, e.EventEndDate, e.EventLocationCity,
               e.EventLocationState, e.EventImage, b.BusinessName AS OrganizerName
        FROM OFNEventRegistrations r
        JOIN OFNEvents e ON r.EventID = e.EventID
        JOIN Business b ON e.BusinessID = b.BusinessID
        WHERE r.PeopleID = :pid
        ORDER BY r.RegDate DESC
    """), {"pid": people_id}).fetchall()
    return [dict(r._mapping) for r in rows]


# ── Organizer: view registrations for my event ────────────────────────────────
@router.get("/api/events/{event_id}/registrations")
def event_registrations(event_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT r.RegID, r.RegDate, r.TotalAmount, r.PaymentStatus,
               r.AttendeeFirstName, r.AttendeeLastName, r.AttendeeEmail, r.AttendeePhone, r.Notes
        FROM OFNEventRegistrations r
        WHERE r.EventID = :eid
        ORDER BY r.RegDate DESC
    """), {"eid": event_id}).fetchall()
    result = []
    for row in rows:
        d = dict(row._mapping)
        items = db.execute(text("""
            SELECT * FROM OFNEventRegistrationItems WHERE RegID = :rid
        """), {"rid": d["RegID"]}).fetchall()
        d["items"] = [dict(i._mapping) for i in items]
        result.append(d)
    return result


# ── Update registration payment status ───────────────────────────────────────
@router.put("/api/events/registrations/{reg_id}")
def update_registration(reg_id: int, data: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        UPDATE OFNEventRegistrations SET PaymentStatus = :status WHERE RegID = :rid
    """), {"rid": reg_id, "status": data.get("PaymentStatus", "pending")})
    db.commit()
    return {"ok": True}
