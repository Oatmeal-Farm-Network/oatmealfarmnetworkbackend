from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from auth import create_access_token, get_current_user
import models
from sqlalchemy import select

router = APIRouter(prefix="/auth", tags=["auth"])

# -------------------------
# Pydantic models
# -------------------------
class LoginRequest(BaseModel):
    Email: str
    Password: str

class ForgotPasswordRequest(BaseModel):
    Email: str


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

        token = create_access_token(data={"sub": user.PeopleID})

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
# My businesses
# -------------------------
@router.get("/my-businesses")
def GetMyBusinesses(PeopleID: int, Db: Session = Depends(get_db)):
    Businesses = (
        Db.query(models.Business)
        .join(models.BusinessAccess, models.Business.BusinessID == models.BusinessAccess.BusinessID)
        .filter(
            models.BusinessAccess.PeopleID == PeopleID,
            models.BusinessAccess.Active == 1
        )
        .all()
    )
    return [{"BusinessID": B.BusinessID, "BusinessName": B.BusinessName} for B in Businesses]


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
        .join(models.Address, models.Business.AddressID == models.Address.AddressID)
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
        "AddressCity": A.AddressCity,
        "AddressState": A.AddressState,
        "AddressStreet": A.AddressStreet,
        "AddressZip": A.AddressZip,
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
    stmt = (
        select(
            models.Animal.AnimalID,
            models.Animal.FullName,
            models.Animal.SpeciesID,
            models.Animal.PublishForSale,
            models.Pricing.Price,
            models.Pricing.StudFee,
            models.Pricing.SalePrice,
            models.SpeciesAvailable.SpeciesPriority
        )
        .join(models.SpeciesAvailable, models.Animal.SpeciesID == models.SpeciesAvailable.SpeciesID)
        .outerjoin(models.Pricing, models.Animal.AnimalID == models.Pricing.AnimalID)
        .where(models.Animal.BusinessID == BusinessID)
        .order_by(models.SpeciesAvailable.SpeciesPriority, models.Animal.FullName)
    )

    Results = Db.execute(stmt).all()

    SpeciesMap = {
        2: "Alpaca", 3: "Dog", 4: "Llama", 5: "Horse", 6: "Goat",
        7: "Donkey", 8: "Cattle", 9: "Bison", 10: "Sheep", 11: "Rabbit",
        12: "Pig", 13: "Chicken", 14: "Turkey", 15: "Duck", 17: "Yak",
        18: "Camels", 19: "Emus", 21: "Deer", 22: "Geese", 23: "Bees",
        25: "Alligators", 26: "Guinea Fowl", 27: "Musk Ox", 28: "Ostriches",
        29: "Pheasants", 30: "Pigeons", 31: "Quails", 33: "Snails", 34: "Buffalo"
    }

    Animals = []
    for row in Results:
        A_ID, A_Name, A_SpeciesID, A_Publish, P_Price, P_StudFee, P_SalePrice, _ = row
        Animals.append({
            "AnimalID": A_ID,
            "FullName": A_Name,
            "SpeciesID": A_SpeciesID,
            "SpeciesName": SpeciesMap.get(A_SpeciesID, "Unknown"),
            "Price": float(P_Price) if P_Price else 0,
            "StudFee": float(P_StudFee) if P_StudFee else 0,
            "SalePrice": float(P_SalePrice) if P_SalePrice else 0,
            "PublishForSale": A_Publish,
        })

    return Animals


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
            text("SELECT RegistrationType FROM SpeciesRegistrationLookup WHERE SpeciesID = :sid ORDER BY RegistrationType"),
            {"sid": species_id}
        ).fetchall()
        return [{"type": r.RegistrationType} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# Add animal
# -------------------------
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

        db.execute(text("""
            INSERT INTO Animals (
                BusinessID, FullName, SpeciesID, NumberofAnimals, Category,
                DOBDay, DOBMonth, DOBYear,
                BreedID, BreedID2, BreedID3, BreedID4,
                Height, Weight, Gaited, Warmblooded, Horns, Temperment,
                Description, AncestryDescription,
                PublishForSale, CoOwnerName1, CoOwnerLink1, CoOwnerBusiness1,
                CoOwnerName2, CoOwnerLink2, CoOwnerBusiness2,
                CoOwnerName3, CoOwnerLink3, CoOwnerBusiness3
            ) VALUES (
                :business_id, :name, :species_id, :num_animals, :category,
                :dob_day, :dob_month, :dob_year,
                :breed1, :breed2, :breed3, :breed4,
                :height, :weight, :gaited, :Warmblooded, :horns, :temperament,
                :description, :ancestry_desc,
                :for_sale, :co_name1, :co_link1, :co_biz1,
                :co_name2, :co_link2, :co_biz2,
                :co_name3, :co_link3, :co_biz3
            )
        """), {
            "business_id": i("BusinessID"), "name": f("Name"), "species_id": i("SpeciesID"),
            "num_animals": i("NumberOfAnimals"), "category": f("Category"),
            "dob_day": i("DOBDay"), "dob_month": i("DOBMonth"), "dob_year": i("DOBYear"),
            "breed1": i("BreedID"), "breed2": i("BreedID2"), "breed3": i("BreedID3"), "breed4": i("BreedID4"),
            "height": n("Height"), "weight": n("Weight"), "gaited": f("Gaited"),
            "Warmblooded": f("Warmblooded"), "horns": f("Horns"), "temperament": i("Temperament"),
            "description": f("Description"), "ancestry_desc": f("AncestryDescription"),
            "for_sale": 1 if f("ForSale") == "Yes" else 0,
            "co_name1": f("CoOwnerName1"), "co_link1": f("CoOwnerLink1"), "co_biz1": f("CoOwnerBusiness1"),
            "co_name2": f("CoOwnerName2"), "co_link2": f("CoOwnerLink2"), "co_biz2": f("CoOwnerBusiness2"),
            "co_name3": f("CoOwnerName3"), "co_link3": f("CoOwnerLink3"), "co_biz3": f("CoOwnerBusiness3"),
        })
        new_id = db.execute(text("SELECT SCOPE_IDENTITY() AS id")).fetchone()
        db.commit()
        return {"message": "Animal added successfully", "AnimalID": int(new_id.id)}
    except Exception as e:
        db.rollback()
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))