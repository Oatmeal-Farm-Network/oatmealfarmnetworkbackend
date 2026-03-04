from fastapi import APIRouter, Depends, HTTPException, status
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
    # Only select the columns needed
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
