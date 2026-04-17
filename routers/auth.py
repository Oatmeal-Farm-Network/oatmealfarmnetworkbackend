from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from auth import create_access_token, get_current_user
import models
from sqlalchemy import select, text

router = APIRouter(prefix="/auth", tags=["auth"])

# -------------------------
# Pydantic models
# -------------------------
class LoginRequest(BaseModel):
    Email: str
    Password: str

class SignupRequest(BaseModel):
    PeopleFirstName: str
    PeopleLastName: str
    Email: str
    Password: str

class ForgotPasswordRequest(BaseModel):
    Email: str

class UpdateLoginRequest(BaseModel):
    first_name: str = None
    last_name: str = None
    email: str = None
    current_password: str = None
    new_password: str = None


# -------------------------
# Public site settings (no auth required — login/signup pages need this)
# -------------------------
@router.get("/site-settings")
def get_site_settings(db: Session = Depends(get_db)):
    settings = db.query(models.SiteSettings).filter(models.SiteSettings.id == 1).first()
    if not settings:
        # Row missing — return safe defaults (open)
        return {"team_only_login": False, "signup_open": True}
    return {
        "team_only_login": bool(settings.team_only_login),
        "signup_open": bool(settings.signup_open),
    }


# -------------------------
# Signup
# -------------------------
@router.post("/signup")
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    from datetime import datetime

    # Check if signup is currently open
    settings = db.query(models.SiteSettings).filter(models.SiteSettings.id == 1).first()
    if settings and not settings.signup_open:
        raise HTTPException(status_code=403, detail="Registration is currently closed.")

    email = request.Email.strip().lower()

    existing = db.query(models.People).filter(
        models.People.PeopleEmail == email
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with that email already exists.")

    new_user = models.People(
        PeopleFirstName=request.PeopleFirstName.strip(),
        PeopleLastName=request.PeopleLastName.strip(),
        PeopleEmail=email,
        PeoplePassword=request.Password,
        PeopleActive=1,
        accesslevel=0,
        Subscriptionlevel=0,
        PeopleCreationDate=datetime.utcnow(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(data={"sub": str(new_user.PeopleID)})

    return {
        "AccessToken": token,
        "token_type": "bearer",
        "PeopleID": new_user.PeopleID,
        "PeopleFirstName": new_user.PeopleFirstName,
        "PeopleLastName": new_user.PeopleLastName,
        "AccessLevel": new_user.accesslevel or 0,
    }


# -------------------------
# Forgot password
# -------------------------
@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    import os, sendgrid
    from sendgrid.helpers.mail import Mail

    email = body.Email.strip().lower()

    user = db.query(models.People).filter(
        models.People.PeopleEmail == email
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    if not user.PeoplePassword:
        raise HTTPException(status_code=500, detail="No password on file. Please contact support.")

    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
    FROM_EMAIL       = os.getenv("FROM_EMAIL", "john@oatmeal-ai.com")
    SITE_NAME        = os.getenv("SITE_NAME", "Oatmeal Farm Network")

    if not SENDGRID_API_KEY:
        raise HTTPException(status_code=503, detail="Email service not configured.")

    html_body = f"""
    <font face="arial">
    Dear {user.PeopleFirstName},<br><br>
    Your {SITE_NAME} password is provided below:<br><br>
    Your password: <b>{user.PeoplePassword}</b><br><br>
    If you did not request this email, please contact us at 458.225.4903.<br><br>
    Thank You.<br><br>
    Sincerely,<br><br>
    {SITE_NAME}
    </font>
    """

    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        sg.send(Mail(
            from_email=FROM_EMAIL,
            to_emails=email,
            subject=f"Your {SITE_NAME} Password",
            html_content=html_body,
        ))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to send email. Please try again.")

    return {"message": "Password sent", "email": email}


# -------------------------
# Login
# -------------------------
@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(models.People).filter(
            models.People.PeopleEmail == request.Email,
            models.People.PeopleActive == 1
        ).first()
        if not user or user.PeoplePassword != request.Password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        # If team-only login is active, reject accounts with accesslevel < 1
        settings = db.query(models.SiteSettings).filter(models.SiteSettings.id == 1).first()
        if settings and settings.team_only_login and (user.accesslevel or 0) < 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access is currently restricted to team members only."
            )

        token = create_access_token(data={"sub": str(user.PeopleID)})

        return {
            "AccessToken": token,
            "token_type": "bearer",
            "PeopleID": user.PeopleID,
            "PeopleFirstName": user.PeopleFirstName,
            "PeopleLastName": user.PeopleLastName,
            "AccessLevel": user.accesslevel or 0
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise


# -------------------------
# Get current user
# -------------------------
@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    return {
        "PeopleID": current_user.PeopleID,
        "PeopleFirstName": current_user.PeopleFirstName,
        "PeopleLastName": current_user.PeopleLastName,
        "PeopleEmail": current_user.PeopleEmail,
        "AccessLevel": current_user.accesslevel
    }


# -------------------------
# Update login info
# -------------------------
@router.put("/update-login")
def update_login(payload: UpdateLoginRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(models.People).filter(models.People.PeopleID == current_user.PeopleID).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.new_password:
        if not payload.current_password or user.PeoplePassword != payload.current_password:
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.PeoplePassword = payload.new_password

    if payload.email and payload.email.strip().lower() != user.PeopleEmail:
        existing = db.query(models.People).filter(
            models.People.PeopleEmail == payload.email.strip().lower(),
            models.People.PeopleID != user.PeopleID
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="That email is already in use by another account")
        user.PeopleEmail = payload.email.strip().lower()

    if payload.first_name is not None:
        user.PeopleFirstName = payload.first_name.strip()
    if payload.last_name is not None:
        user.PeopleLastName = payload.last_name.strip()

    db.commit()
    return {
        "message": "Settings updated successfully",
        "PeopleFirstName": user.PeopleFirstName,
        "PeopleLastName": user.PeopleLastName,
        "PeopleEmail": user.PeopleEmail,
    }


# -------------------------
# My businesses
# -------------------------
@router.get("/my-businesses")
def GetMyBusinesses(PeopleID: int, Db: Session = Depends(get_db)):
    rows = (
        Db.query(models.Business, models.Address)
        .join(models.BusinessAccess, models.Business.BusinessID == models.BusinessAccess.BusinessID)
        .outerjoin(models.Address, models.Business.AddressID == models.Address.AddressID)
        .filter(
            models.BusinessAccess.PeopleID == PeopleID,
            models.BusinessAccess.Active == 1
        )
        .all()
    )
    return [
        {
            "BusinessID": B.BusinessID,
            "BusinessName": B.BusinessName,
            "BusinessTypeID": B.BusinessTypeID,
            "AddressCity":    A.AddressCity    if A else None,
            "AddressState":   A.AddressState   if A else None,
            "AddressZip":     A.AddressZip     if A else None,
            "AddressCountry": A.AddressCountry if A else None,
        }
        for B, A in rows
    ]


# -------------------------
# Account home
# -------------------------
@router.get("/account-home")
def GetAccountHome(BusinessID: int, Db: Session = Depends(get_db)):
    Result = (
        Db.query(
            models.Business,
            models.BusinessTypeLookup,
            models.Address,
        )
        .join(models.BusinessTypeLookup, models.Business.BusinessTypeID == models.BusinessTypeLookup.BusinessTypeID)
        .outerjoin(models.Address, models.Business.AddressID == models.Address.AddressID)
        .filter(models.Business.BusinessID == BusinessID)
        .first()
    )

    if not Result:
        raise HTTPException(status_code=404, detail="Business not found")

    B, BT, A = Result

    return {
        "BusinessID": B.BusinessID,
        "BusinessName": B.BusinessName,
        "BusinessEmail": B.BusinessEmail,
        "BusinessTypeID": BT.BusinessTypeID,
        "BusinessType": BT.BusinessType,
        "SubscriptionLevel": B.SubscriptionLevel,
        "SubscriptionEndDate": str(B.SubscriptionEndDate) if hasattr(B, 'SubscriptionEndDate') else None,
        "AddressCity": A.AddressCity if A else None,
        "AddressState": A.AddressState if A else None,
        "AddressStreet": A.AddressStreet if A else None,
        "AddressZip": A.AddressZip if A else None,
    }


# -------------------------
# Business types
# -------------------------
@router.get("/business-types")
def GetBusinessTypes(Db: Session = Depends(get_db)):
    Types = Db.query(models.BusinessTypeLookup).order_by(models.BusinessTypeLookup.BusinessType).all()
    return [{"BusinessTypeID": T.BusinessTypeID, "BusinessType": T.BusinessType} for T in Types]


@router.put("/change-business-type")
def ChangeBusinessType(BusinessID: int, BusinessTypeID: int, Db: Session = Depends(get_db)):
    Business = Db.query(models.Business).filter(models.Business.BusinessID == BusinessID).first()
    if not Business:
        raise HTTPException(status_code=404, detail="Business not found")
    Business.BusinessTypeID = BusinessTypeID
    Db.commit()
    return {"status": "success"}


# -------------------------
# Animals endpoint (optimized)
# -------------------------
@router.get("/animals")
def GetAnimals(BusinessID: int, Db: Session = Depends(get_db)):
    rows = Db.execute(text("""
        SELECT
            a.AnimalID,
            a.FullName,
            a.SpeciesID,
            a.PublishForSale,
            a.PublishStud,
            p.Price,
            p.StudFee,
            p.SalePrice,
            sa.PluralTerm AS SpeciesName,
            sc.SpeciesCategory AS CategoryName,
            sc.SpeciesCategoryOrder
        FROM Animals a
        LEFT JOIN SpeciesAvailable sa ON sa.SpeciesID = a.SpeciesID
        LEFT JOIN Pricing p ON p.AnimalID = a.AnimalID
        LEFT JOIN SpeciesCategory sc ON sc.SpeciesCategoryID = a.SpeciesCategoryID
        WHERE a.BusinessID = :bid
        ORDER BY sa.PluralTerm, sc.SpeciesCategoryOrder, a.FullName
    """), {"bid": BusinessID}).fetchall()

    return [
        {
            "AnimalID": r.AnimalID,
            "FullName": r.FullName,
            "SpeciesID": r.SpeciesID,
            "SpeciesName": r.SpeciesName or "Unknown",
            "Category": r.CategoryName or "",
            "Price": float(r.Price) if r.Price else 0,
            "StudFee": float(r.StudFee) if r.StudFee else 0,
            "SalePrice": float(r.SalePrice) if r.SalePrice else 0,
            "PublishForSale": r.PublishForSale,
            "PublishStud": r.PublishStud,
        }
        for r in rows
    ]


# -------------------------
# Species list
# -------------------------
@router.get("/species")
def get_species_list(db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT MIN(SpeciesID) AS SpeciesID, MIN(SingularTerm) AS SingularTerm, PluralTerm "
        "FROM SpeciesAvailable GROUP BY PluralTerm ORDER BY PluralTerm"
    )).fetchall()
    return [{"id": r.SpeciesID, "singular": r.SingularTerm, "plural": r.PluralTerm} for r in rows]


# -------------------------
# Species breeds
# -------------------------
@router.get("/species/{species_id}/breeds")
def get_species_breeds(species_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import text
    try:
        rows = db.execute(
            text("SELECT BreedLookupID, Breed FROM SpeciesBreedLookupTable WHERE SpeciesID = :sid AND LEFT(Breed,1) LIKE '[A-Z]' ORDER BY Breed"),
            {"sid": species_id}
        ).fetchall()
        return [{"id": r.BreedLookupID, "name": r.Breed} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# Species registration types
# -------------------------
@router.get("/species/{species_id}/registration-types")
def get_registration_types(species_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import text
    try:
        rows = db.execute(
            text("SELECT SpeciesRegistrationType FROM SpeciesRegistrationTypeLookupTable "
                 "WHERE SpeciesID = :sid ORDER BY SpeciesRegistrationType"),
            {"sid": species_id}
        ).fetchall()
        return [{"type": r.SpeciesRegistrationType} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# Add animal
# -------------------------
def _upload_animal_photo(file_bytes: bytes, original_filename: str) -> str:
    """Upload a single animal photo to GCS Animals/ and return its public URL."""
    import uuid, os
    from urllib.parse import quote
    from google.cloud import storage as _gcs
    ext  = os.path.splitext(original_filename)[1].lower() or ".webp"
    fname = f"{uuid.uuid4().hex}{ext}"
    bucket = _gcs.Client().bucket("oatmeal-farm-network-images")
    blob   = bucket.blob(f"Animals/{fname}")
    ct_map = {".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    blob.upload_from_string(file_bytes, content_type=ct_map.get(ext, "image/webp"))
    return f"https://storage.googleapis.com/oatmeal-farm-network-images/Animals/{quote(fname, safe='')}"


def _upload_animal_doc(file_bytes: bytes, original_filename: str) -> str:
    """Upload a single animal document (PDF or image) to GCS AnimalDocs/."""
    import uuid, os
    from urllib.parse import quote
    from google.cloud import storage as _gcs
    ext  = os.path.splitext(original_filename)[1].lower() or ".pdf"
    fname = f"{uuid.uuid4().hex}{ext}"
    bucket = _gcs.Client().bucket("oatmeal-farm-network-images")
    blob   = bucket.blob(f"AnimalDocs/{fname}")
    ct_map = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".png": "image/png", ".webp": "image/webp"}
    blob.upload_from_string(file_bytes, content_type=ct_map.get(ext, "application/octet-stream"))
    return f"https://storage.googleapis.com/oatmeal-farm-network-images/AnimalDocs/{quote(fname, safe='')}"


# ── People search (for testimonials etc.) ─────────────────────────────────────

@router.get("/people/search")
def search_people(q: str, db: Session = Depends(get_db)):
    from sqlalchemy import text
    if not q or len(q.strip()) < 2:
        return []
    term = f"%{q.strip()}%"
    rows = db.execute(text("""
        SELECT TOP 20
            p.PeopleID,
            p.PeopleFirstName,
            p.PeopleLastName,
            a.AddressCity  AS City,
            a.AddressState AS State,
            b.BusinessID,
            b.BusinessName,
            b.BusinessBlog AS ExternalWebsite,
            bw.Slug        AS OFNSlug
        FROM People p
        LEFT JOIN Address a ON a.AddressID = p.AddressID
        LEFT JOIN BusinessAccess ba ON ba.PeopleID = p.PeopleID AND ba.Active = 1
        LEFT JOIN Business b ON b.BusinessID = ba.BusinessID
        LEFT JOIN BusinessWebsite bw ON bw.BusinessID = b.BusinessID
        WHERE p.PeopleActive = 1
          AND (p.PeopleFirstName LIKE :q OR p.PeopleLastName LIKE :q
               OR (p.PeopleFirstName + ' ' + p.PeopleLastName) LIKE :q)
        ORDER BY p.PeopleFirstName, p.PeopleLastName
    """), {"q": term}).fetchall()
    results = []
    for r in rows:
        d = dict(r._mapping)
        # Build Website URL: prefer OFN site, then external website, then ranch profile
        if d.get("OFNSlug"):
            d["Website"] = f"https://www.OatmealFarmNetwork.com/sites/{d['OFNSlug']}"
        elif d.get("ExternalWebsite"):
            d["Website"] = d["ExternalWebsite"]
        elif d.get("BusinessID"):
            d["Website"] = f"https://www.OatmealFarmNetwork.com/marketplaces/livestock/ranch/{d['BusinessID']}"
        else:
            d["Website"] = ""
        del d["OFNSlug"]
        del d["ExternalWebsite"]
        results.append(d)
    return results


@router.post("/animals/add")
async def add_animal(
    request: Request,
    db: Session = Depends(get_db),
):
    from sqlalchemy import text
    try:
        form = await request.form()
        def f(key): return form.get(key) or None
        def n(key): v = form.get(key); return float(v) if v else None
        def i(key): v = form.get(key); return int(v) if v else None

        business_id = i("BusinessID")

        # Look up PeopleID from BusinessAccess
        ba_row = db.execute(text(
            "SELECT TOP 1 PeopleID FROM BusinessAccess WHERE BusinessID = :bid AND Active = 1"
        ), {"bid": business_id}).fetchone()
        people_id = ba_row.PeopleID if ba_row else None

        db.execute(text("""
            INSERT INTO Animals (
                BusinessID, PeopleID, FullName, SpeciesID, NumberofAnimals, SpeciesCategoryID,
                DOBDay, DOBMonth, DOBYear,
                BreedID, BreedID2, BreedID3, BreedID4,
                Height, Weight, Gaited, Warmblooded, Horns, Temperment,
                Description, AncestryDescription,
                PublishForSale, CoOwnerName1, CoOwnerLink1, CoOwnerBusiness1,
                CoOwnerName2, CoOwnerLink2, CoOwnerBusiness2,
                CoOwnerName3, CoOwnerLink3, CoOwnerBusiness3,
                PercentPeruvian, PercentChilean, PercentBolivian,
                PercentUnknownOther, PercentAccoyo
            ) VALUES (
                :business_id, :people_id, :name, :species_id, :num_animals, :species_category_id,
                :dob_day, :dob_month, :dob_year,
                :breed1, :breed2, :breed3, :breed4,
                :height, :weight, :gaited, :warmblood, :horns, :temperament,
                :description, :ancestry_desc,
                :for_sale, :co_name1, :co_link1, :co_biz1,
                :co_name2, :co_link2, :co_biz2,
                :co_name3, :co_link3, :co_biz3,
                :pct_peruvian, :pct_chilean, :pct_bolivian,
                :pct_unknown, :pct_accoyo
            )
        """), {
            "business_id": business_id, "people_id": people_id,
            "name": f("Name"), "species_id": i("SpeciesID"),
            "num_animals": i("NumberOfAnimals"), "species_category_id": i("SpeciesCategoryID"),
            "dob_day": i("DOBDay"), "dob_month": i("DOBMonth"), "dob_year": i("DOBYear"),
            "breed1": i("BreedID"), "breed2": i("BreedID2"), "breed3": i("BreedID3"), "breed4": i("BreedID4"),
            "height": n("Height"), "weight": n("Weight"), "gaited": f("Gaited"),
            "warmblood": f("Warmblood"), "horns": f("Horns"), "temperament": i("Temperament"),
            "description": f("Description"), "ancestry_desc": f("AncestryDescription"),
            "for_sale": 1 if f("ForSale") == "Yes" else 0,
            "co_name1": f("CoOwnerName1"), "co_link1": f("CoOwnerLink1"), "co_biz1": f("CoOwnerBusiness1"),
            "co_name2": f("CoOwnerName2"), "co_link2": f("CoOwnerLink2"), "co_biz2": f("CoOwnerBusiness2"),
            "co_name3": f("CoOwnerName3"), "co_link3": f("CoOwnerLink3"), "co_biz3": f("CoOwnerBusiness3"),
            "pct_peruvian": f("PercentPeruvian"), "pct_chilean": f("PercentChilean"),
            "pct_bolivian": f("PercentBolivian"), "pct_unknown": f("PercentUnknownOther"),
            "pct_accoyo": f("PercentAccoyo"),
        })
        new_id = db.execute(text("SELECT SCOPE_IDENTITY() AS id")).fetchone()
        animal_id = int(new_id.id)

        # Create Pricing row
        # ForSale is stored as PublishForSale on the Animals table (set above),
        # NOT in the Pricing table.
        db.execute(text("""
            INSERT INTO Pricing (
                AnimalID, Price, StudFee, EmbryoPrice, SemenPrice,
                Free, Sold, PriceComments, Financeterms
            ) VALUES (
                :aid, :price, :stud, :embryo, :semen,
                :free, 0, :comments, :terms
            )
        """), {
            "aid":      animal_id,
            "price":    n("Price"),
            "stud":     n("StudFee"),
            "embryo":   n("EmbryoPrice"),
            "semen":    n("SemenPrice"),
            "free":     1 if f("Free") == "Yes" else 0,
            "comments": f("PriceComments"),
            "terms":    f("Financeterms"),
        })

        # Upload photos to GCS and create Photos row
        photo_urls = {}
        photo_captions = {}
        for idx in range(1, 9):
            file_field = form.get(f"Photo{idx}")
            if file_field and hasattr(file_field, "read"):
                try:
                    data = await file_field.read()
                    if data:
                        url = _upload_animal_photo(data, file_field.filename)
                        photo_urls[f"Photo{idx}"] = url
                except Exception:
                    pass
            cap = form.get(f"Caption{idx}")
            if cap:
                photo_captions[f"PhotoCaption{idx}"] = cap

        # Resolve cover slot → ListPageImage url (if slot was uploaded this request)
        cover_slot_raw = form.get("CoverPhotoSlot")
        list_page_image = None
        try:
            cover_slot = int(cover_slot_raw) if cover_slot_raw else 0
        except (TypeError, ValueError):
            cover_slot = 0
        if 1 <= cover_slot <= 8:
            list_page_image = photo_urls.get(f"Photo{cover_slot}")
        # Fallback: if cover slot had no new upload, use first uploaded photo
        if not list_page_image and photo_urls:
            first_key = sorted(photo_urls.keys())[0]
            list_page_image = photo_urls[first_key]

        insert_cols = {}
        insert_cols.update(photo_urls)
        insert_cols.update(photo_captions)
        if list_page_image:
            insert_cols["ListPageImage"] = list_page_image

        # Document uploads: registration certificate → ARI column, histogram → Histogram column
        for form_field, db_col in (("AriDoc", "ARI"), ("HistogramDoc", "Histogram")):
            f_doc = form.get(form_field)
            if f_doc and hasattr(f_doc, "read"):
                try:
                    data = await f_doc.read()
                    if data:
                        insert_cols[db_col] = _upload_animal_doc(data, f_doc.filename or f"{db_col}.pdf")
                except Exception:
                    pass

        if insert_cols:
            cols   = ", ".join(insert_cols.keys())
            params = {k.lower(): v for k, v in insert_cols.items()}
            vals   = ", ".join(f":{k.lower()}" for k in insert_cols)
            db.execute(text(
                f"INSERT INTO Photos (AnimalID, {cols}) VALUES (:aid, {vals})"
            ), {"aid": animal_id, **params})
        else:
            # Always create an empty Photos row so the edit page can update it
            db.execute(text("INSERT INTO Photos (AnimalID) VALUES (:aid)"), {"aid": animal_id})

        import json as _json

        # Insert fiber samples if provided
        fiber_json = form.get("FiberSamples")
        if fiber_json:
            def _nf(v): return float(v) if v else None
            def _ni(v): return int(v) if v else None
            for s in _json.loads(fiber_json):
                year = _ni(s.get("sampleYear"))
                avg  = _nf(s.get("afd"))
                if year or avg:
                    db.execute(text("""
                        INSERT INTO Fiber (
                            AnimalID, SampleDateYear, Average, CF, StandardDev,
                            CrimpPerInch, COV, Length, GreaterThan30,
                            ShearWeight, Curve, BlanketWeight
                        ) VALUES (
                            :aid, :year, :avg, :cf, :sd, :cpi, :cov,
                            :length, :gt30, :sw, :curve, :bw
                        )
                    """), {
                        "aid":    animal_id,
                        "year":   year,
                        "avg":    avg,
                        "cf":     _nf(s.get("cf")),
                        "sd":     _nf(s.get("sd")),
                        "cpi":    _nf(s.get("crimpsPerInch")),
                        "cov":    _nf(s.get("cov")),
                        "length": _nf(s.get("stapleLength")),
                        "gt30":   _nf(s.get("gt30")),
                        "sw":     _nf(s.get("shearWeight")),
                        "curve":  _nf(s.get("curve")),
                        "bw":     _nf(s.get("blanketWeight")),
                    })

        # Insert colors if provided
        color1, color2 = f("Color1"), f("Color2")
        color3, color4 = f("Color3"), f("Color4")
        if any([color1, color2, color3, color4]):
            db.execute(text("""
                INSERT INTO Colors (AnimalID, Color1, Color2, Color3, Color4)
                VALUES (:aid, :c1, :c2, :c3, :c4)
            """), {"aid": animal_id, "c1": color1, "c2": color2, "c3": color3, "c4": color4})

        # Insert ancestry if provided
        anc_json = form.get("AncestryJSON")
        if anc_json:
            anc = _json.loads(anc_json)
            ANC_MAP = {
                "sire":        "Sire",
                "dam":         "Dam",
                "sireSire":    "SireSire",
                "sireDam":     "SireDam",
                "damSire":     "DamSire",
                "damDam":      "DamDam",
                "sireSireSire":"SireSireSire",
                "sireSireDam": "SireSireDam",
                "sireDamSire": "SireDamSire",
                "sireDamDam":  "SireDamDam",
                "damSireSire": "DamSireSire",
                "damSireDam":  "DamSireDam",
                "damDamSire":  "DamDamSire",
                "damDamDam":   "DamDamDam",
            }
            # Only proceed if any ancestor has data
            has_anc = any(
                (anc.get(k) or {}).get("name") or (anc.get(k) or {}).get("color")
                for k in ANC_MAP
            )
            if has_anc:
                all_fields = []
                params = {"aid": animal_id}
                for js_key, db_prefix in ANC_MAP.items():
                    val = anc.get(js_key) or {}
                    all_fields += [db_prefix, f"{db_prefix}Color", f"{db_prefix}Link", f"{db_prefix}ARI"]
                    params[db_prefix]           = val.get("name")  or None
                    params[f"{db_prefix}Color"] = val.get("color") or None
                    params[f"{db_prefix}Link"]  = val.get("link")  or None
                    params[f"{db_prefix}ARI"]   = val.get("ari")   or None
                existing = db.execute(text("SELECT COUNT(*) FROM Ancestors WHERE AnimalID = :aid"),
                                      {"aid": animal_id}).scalar()
                if existing:
                    set_clause = ", ".join(f"{fld} = :{fld}" for fld in all_fields)
                    db.execute(text(f"UPDATE Ancestors SET {set_clause} WHERE AnimalID = :aid"), params)
                else:
                    cols = ", ".join(["AnimalID"] + all_fields)
                    vals = ", ".join([":aid"] + [f":{fld}" for fld in all_fields])
                    db.execute(text(f"INSERT INTO Ancestors ({cols}) VALUES ({vals})"), params)

        # Insert awards if provided
        awards_json = form.get("AwardsJSON")
        if awards_json:
            for aw in _json.loads(awards_json):
                if aw.get("year") or aw.get("show") or aw.get("placing"):
                    db.execute(text("""
                        INSERT INTO awards (AnimalID, AwardYear, ShowName, Type, Placing, Awardcomments)
                        VALUES (:aid, :year, :show, :aclass, :placing, :comments)
                    """), {
                        "aid":      animal_id,
                        "year":     aw.get("year")        or None,
                        "show":     aw.get("show")        or None,
                        "aclass":   aw.get("class")       or None,
                        "placing":  aw.get("placing")     or None,
                        "comments": aw.get("description") or None,
                    })

        # Insert registrations if provided
        regs_json = form.get("RegistrationsJSON")
        if regs_json:
            for reg in _json.loads(regs_json):
                if (reg.get("number") or "").strip():
                    db.execute(text("""
                        INSERT INTO animalregistration (AnimalID, RegType, RegNumber)
                        VALUES (:aid, :reg_type, :reg_num)
                    """), {
                        "aid":      animal_id,
                        "reg_type": reg.get("type")   or None,
                        "reg_num":  reg.get("number") or None,
                    })

        db.commit()
        return {"message": "Animal added successfully", "AnimalID": animal_id}
    except Exception as e:
        db.rollback()
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ── Testimonials ──────────────────────────────────────────────────────────────

@router.get("/testimonials")
def get_testimonials(BusinessID: int, db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT TestimonialsID, CustomerName AS AuthorName,
               Testimonial AS Content, Rating,
               City, State, Organization, URL AS Website,
               TestimonialDate, PeopleID, Name,
               AnimalID, AnimalName, TestimonialsType
        FROM Testimonials
        WHERE CustID = :bid
        ORDER BY testimonialsOrder, TestimonialsID DESC
    """), {"bid": BusinessID}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/testimonials/add")
async def add_testimonial(request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import text
    body = await request.json()
    # Get next sort order
    max_order = db.execute(text(
        "SELECT ISNULL(MAX(testimonialsOrder), 0) FROM Testimonials WHERE CustID = :bid"
    ), {"bid": body.get("BusinessID")}).scalar()
    db.execute(text("""
        INSERT INTO Testimonials (
            CustID, CustomerName, Testimonial, Rating,
            City, State, Organization, URL,
            TestimonialDate, PeopleID, testimonialsOrder
        ) VALUES (
            :cust_id, :customer_name, :testimonial, :rating,
            :city, :state, :organization, :url,
            :testimonial_date, :people_id, :sort_order
        )
    """), {
        "cust_id": body.get("BusinessID"),
        "customer_name": body.get("AuthorName"),
        "testimonial": body.get("Content"),
        "rating": body.get("Rating"),
        "city": body.get("City") or None,
        "state": body.get("State") or None,
        "organization": body.get("Organization") or None,
        "url": body.get("Website") or None,
        "testimonial_date": body.get("TestimonialDate") or None,
        "people_id": body.get("PeopleID") or None,
        "sort_order": (max_order or 0) + 1,
    })
    db.commit()
    return {"message": "Testimonial added"}


@router.post("/testimonials/update")
async def update_testimonial(request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import text
    body = await request.json()
    tid = body.get("TestimonialsID")
    if not tid:
        return {"error": "TestimonialsID required"}
    db.execute(text("""
        UPDATE Testimonials SET
            CustomerName = :customer_name,
            Testimonial = :testimonial,
            Rating = :rating,
            City = :city,
            State = :state,
            Organization = :organization,
            URL = :url,
            TestimonialDate = :testimonial_date,
            PeopleID = :people_id
        WHERE TestimonialsID = :tid
    """), {
        "customer_name": body.get("AuthorName"),
        "testimonial": body.get("Content"),
        "rating": body.get("Rating"),
        "city": body.get("City") or None,
        "state": body.get("State") or None,
        "organization": body.get("Organization") or None,
        "url": body.get("Website") or None,
        "testimonial_date": body.get("TestimonialDate") or None,
        "people_id": body.get("PeopleID") or None,
        "tid": tid,
    })
    db.commit()
    return {"message": "Testimonial updated"}


# ── Animal Packages ─────────────────────────────────────────────
@router.get("/packages")
def get_packages(BusinessID: int, db: Session = Depends(get_db)):
    from sqlalchemy import text
    # Ensure tables exist
    db.execute(text("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'AnimalPackage')
        BEGIN
            CREATE TABLE AnimalPackage (
                PackageID INT IDENTITY(1,1) PRIMARY KEY,
                BusinessID INT NOT NULL,
                Title NVARCHAR(200) NOT NULL,
                Description NVARCHAR(MAX),
                PackagePrice DECIMAL(10,2),
                CreatedAt DATETIME DEFAULT GETDATE()
            )
        END
    """))
    db.execute(text("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'AnimalPackageItem')
        BEGIN
            CREATE TABLE AnimalPackageItem (
                PackageItemID INT IDENTITY(1,1) PRIMARY KEY,
                PackageID INT NOT NULL,
                AnimalID INT NOT NULL,
                IncludeType VARCHAR(20) NOT NULL DEFAULT 'sale',
                FOREIGN KEY (PackageID) REFERENCES AnimalPackage(PackageID)
            )
        END
    """))
    db.commit()

    rows = db.execute(text("""
        SELECT p.PackageID, p.Title, p.Description, p.PackagePrice, p.CreatedAt
        FROM AnimalPackage p
        WHERE p.BusinessID = :bid
        ORDER BY p.CreatedAt DESC
    """), {"bid": BusinessID}).fetchall()

    packages = []
    for r in rows:
        items = db.execute(text("""
            SELECT pi.PackageItemID, pi.AnimalID, pi.IncludeType,
                   a.FullName,
                   pr.Price, pr.SalePrice, pr.StudFee
            FROM AnimalPackageItem pi
            JOIN Animals a ON a.AnimalID = pi.AnimalID
            LEFT JOIN Pricing pr ON pr.AnimalID = pi.AnimalID
            WHERE pi.PackageID = :pid
        """), {"pid": r.PackageID}).fetchall()

        pkg_items = []
        for it in items:
            price = float(it.SalePrice) if it.SalePrice else (float(it.Price) if it.Price else 0)
            stud_fee = float(it.StudFee) if it.StudFee else 0
            pkg_items.append({
                "PackageItemID": it.PackageItemID,
                "AnimalID": it.AnimalID,
                "FullName": it.FullName,
                "IncludeType": it.IncludeType,
                "Price": price,
                "StudFee": stud_fee,
            })

        packages.append({
            "PackageID": r.PackageID,
            "Title": r.Title,
            "Description": r.Description,
            "PackagePrice": float(r.PackagePrice) if r.PackagePrice else 0,
            "CreatedAt": str(r.CreatedAt) if r.CreatedAt else None,
            "Items": pkg_items,
        })
    return packages


@router.post("/packages/save")
async def save_package(request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import text
    body = await request.json()
    pkg_id = body.get("PackageID")
    biz_id = body.get("BusinessID")
    title = body.get("Title")
    desc = body.get("Description") or None
    price = body.get("PackagePrice")
    items = body.get("Items", [])

    if pkg_id:
        db.execute(text("""
            UPDATE AnimalPackage SET Title = :title, Description = :desc, PackagePrice = :price
            WHERE PackageID = :pid
        """), {"title": title, "desc": desc, "price": price, "pid": pkg_id})
        db.execute(text("DELETE FROM AnimalPackageItem WHERE PackageID = :pid"), {"pid": pkg_id})
    else:
        result = db.execute(text("""
            INSERT INTO AnimalPackage (BusinessID, Title, Description, PackagePrice)
            OUTPUT INSERTED.PackageID
            VALUES (:bid, :title, :desc, :price)
        """), {"bid": biz_id, "title": title, "desc": desc, "price": price})
        pkg_id = result.fetchone()[0]

    for it in items:
        db.execute(text("""
            INSERT INTO AnimalPackageItem (PackageID, AnimalID, IncludeType)
            VALUES (:pid, :aid, :itype)
        """), {"pid": pkg_id, "aid": it["AnimalID"], "itype": it.get("IncludeType", "sale")})

    db.commit()
    return {"message": "Package saved", "PackageID": pkg_id}


@router.post("/packages/delete")
async def delete_package(request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import text
    body = await request.json()
    pid = body.get("PackageID")
    db.execute(text("DELETE FROM AnimalPackageItem WHERE PackageID = :pid"), {"pid": pid})
    db.execute(text("DELETE FROM AnimalPackage WHERE PackageID = :pid"), {"pid": pid})
    db.commit()
    return {"message": "Package deleted"}