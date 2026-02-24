from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models

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
        results = (
            db.query(models.StateProvince.name)
            .join(models.Country, models.StateProvince.country_id == models.Country.country_id)
            .filter(models.Country.name == country)
            .filter(models.StateProvince.name != None)
            .order_by(models.StateProvince.name)
            .all()
        )
        return [r[0] for r in results if r[0]]
    except Exception as e:
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

        # Sort: businesses with logos first, then alphabetically by name
        query = query.order_by(
            models.Business.Logo.is_(None),
            models.Business.Logo == "0",
            models.Business.BusinessName
        )

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
