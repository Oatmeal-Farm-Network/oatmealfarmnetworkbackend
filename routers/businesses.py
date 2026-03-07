from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import datetime

router = APIRouter(prefix="/api/businesses", tags=["businesses"])


def clean(val):
    """Return None if value is null, '0', or empty string."""
    if val is None:
        return None
    if str(val).strip() in ("0", ""):
        return None
    return val


def build_logo_url(logo):
    """Build full logo URL handling /uploads/ prefix or bare filename."""
    if not logo or str(logo).strip() in ("0", ""):
        return None
    if logo.startswith("/"):
        return "https://www.oatmealfarmnetwork.com" + logo
    return "https://www.oatmealfarmnetwork.com/uploads/" + logo


@router.get("/countries")
def get_countries(db: Session = Depends(get_db)):
    try:
        countries = db.query(models.Country.name).order_by(models.Country.name).all()
        return [c[0] for c in countries if c[0]]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/states")
def get_states(country: str, db: Session = Depends(get_db)):
    try:
        from sqlalchemy import text
        rows = db.execute(
            text("""SELECT sp.StateIndex, sp.name
                    FROM state_province sp
                    JOIN country c ON sp.country_id = c.country_id
                    WHERE c.name = :country
                    ORDER BY sp.name"""),
            {"country": country}
        ).fetchall()
        return [{"StateIndex": r.StateIndex, "name": r.name} for r in rows]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types")
def get_business_types(db: Session = Depends(get_db)):
    try:
        from sqlalchemy import text
        rows = db.execute(
            text("SELECT BusinessTypeID, BusinessType FROM businesstypelookup ORDER BY BusinessType")
        ).fetchall()
        return [{"BusinessTypeID": r.BusinessTypeID, "BusinessType": r.BusinessType} for r in rows]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
def create_account(payload: dict, db: Session = Depends(get_db)):
    try:
        from sqlalchemy import text

        people_id = payload.get("PeopleID")
        if not people_id:
            raise HTTPException(status_code=400, detail="PeopleID is required")

        # 1. Create Address record
        address = models.Address(
            AddressStreet = payload.get("AddressStreet", ""),
            AddressCity   = payload.get("AddressCity", ""),
            AddressState  = payload.get("StateIndex", ""),
            AddressZip    = payload.get("AddressZip", ""),
        )
        db.add(address)
        db.flush()

        # 2. Create Websites record if website provided
        websites_id = None
        website = payload.get("BusinessWebsite", "")
        if website:
            ws = models.Websites(Website=website)
            db.add(ws)
            db.flush()
            websites_id = ws.WebsitesID

        # 3. Create Business record
        business = models.Business(
            BusinessTypeID    = payload.get("BusinessTypeID"),
            BusinessName      = payload.get("BusinessName", ""),
            AddressID         = address.AddressID,
            WebsitesID        = websites_id,
            SubscriptionLevel = 0,
            AccessLevel       = 1,
        )
        db.add(business)
        db.flush()

        # 4. Create BusinessAccess record linking user to business
        access = models.BusinessAccess(
            BusinessID    = business.BusinessID,
            PeopleID      = int(people_id),
            AccessLevelID = 1,
            Active        = 1,
            CreatedAt     = datetime.datetime.utcnow(),
            Role          = "Owner",
        )
        db.add(access)

        # 5. Update People phone if provided
        phone = payload.get("PeoplePhone", "")
        if phone:
            db.execute(
                text("UPDATE People SET PeoplePhone = :phone WHERE PeopleID = :pid"),
                {"phone": phone, "pid": int(people_id)}
            )

        db.commit()
        return {"BusinessID": business.BusinessID, "message": "Account created successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug")
def debug_businesses(db: Session = Depends(get_db)):
    countries = db.query(models.Country.name).limit(20).all()
    sample = (
        db.query(models.Business.BusinessName, models.Country.name)
        .join(models.Address, models.Business.AddressID == models.Address.AddressID)
        .join(models.Country, models.Address.country_id == models.Country.country_id)
        .limit(10)
        .all()
    )
    return {
        "countries": [c[0] for c in countries],
        "sample_businesses": [{"name": b[0], "country": b[1]} for b in sample]
    }


@router.get("/")
def get_businesses(
    country: str = None,
    BusinessTypeID: int = None,
    state: str = None,
    db: Session = Depends(get_db)
):
    try:
        query = (
            db.query(
                models.Business,
                models.Address,
                models.BusinessTypeLookup,
                models.Country,
                models.Websites
            )
            .outerjoin(models.Address, models.Business.AddressID == models.Address.AddressID)
            .outerjoin(models.BusinessTypeLookup, models.Business.BusinessTypeID == models.BusinessTypeLookup.BusinessTypeID)
            .outerjoin(models.Country, models.Address.country_id == models.Country.country_id)
            .outerjoin(models.Websites, models.Business.WebsitesID == models.Websites.WebsitesID)
        )

        if BusinessTypeID:
            query = query.filter(models.Business.BusinessTypeID == BusinessTypeID)
        if country:
            query = query.filter(models.Country.name == country)
        if state:
            query = query.filter(models.Address.AddressState == state)

        query = query.order_by(models.Business.BusinessName)
        results = query.all()

        businesses = []
        for B, A, BT, C, W in results:
            businesses.append({
                "BusinessID":           B.BusinessID,
                "BusinessName":         B.BusinessName,
                "BusinessEmail":        B.BusinessEmail,
                "BusinessPhone":        B.BusinessPhone,
                "BusinessTypeID":       B.BusinessTypeID,
                "BusinessType":         BT.BusinessType if BT else None,
                "AddressStreet":        clean(A.AddressStreet if A else None),
                "AddressCity":          clean(A.AddressCity if A else None),
                "AddressState":         clean(A.AddressState if A else None),
                "AddressZip":           clean(A.AddressZip if A else None),
                "AddressCountry":       C.name if C else None,
                "ProfileImage":         build_logo_url(B.Logo),
                "BusinessWebsite":      W.Website if W and W.Website else None,
                "BusinessFacebook":     B.BusinessFacebook,
                "BusinessInstagram":    B.BusinessInstagram,
                "BusinessLinkedIn":     B.BusinessLinkedIn,
                "BusinessX":            B.BusinessX,
                "BusinessPinterest":    B.BusinessPinterest,
                "BusinessYouTube":      B.BusinessYouTube,
                "BusinessTruthSocial":  B.BusinessTruthSocial,
                "BusinessBlog":         B.BusinessBlog,
                "BusinessOtherSocial1": B.BusinessOtherSocial1,
                "BusinessOtherSocial2": B.BusinessOtherSocial2,
            })

        return businesses

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))