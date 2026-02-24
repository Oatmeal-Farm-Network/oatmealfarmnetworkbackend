from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from auth import create_access_token, get_current_user
import models

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    Email: str
    Password: str

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

@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    return {
        "PeopleID": current_user.PeopleID,
        "PeopleFirstName": current_user.PeopleFirstName,
        "PeopleLastName": current_user.PeopleLastName,
        "PeopleEmail": current_user.PeopleEmail,
        "AccessLevel": current_user.accesslevel
    }

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



@router.get("/animals")
def GetAnimals(BusinessID: int, Db: Session = Depends(get_db)):
    Results = (
        Db.query(
            models.Animal,
            models.SpeciesAvailable,
            models.Pricing
        )
        .join(models.SpeciesAvailable, models.Animal.SpeciesID == models.SpeciesAvailable.SpeciesID)
        .outerjoin(models.Pricing, models.Animal.AnimalID == models.Pricing.AnimalID)
        .filter(models.Animal.BusinessID == BusinessID)
        .order_by(models.SpeciesAvailable.SpeciesPriority, models.Animal.FullName)
        .all()
    )

    SpeciesMap = {
        2: "Alpaca", 3: "Dog", 4: "Llama", 5: "Horse", 6: "Goat",
        7: "Donkey", 8: "Cattle", 9: "Bison", 10: "Sheep", 11: "Rabbit",
        12: "Pig", 13: "Chicken", 14: "Turkey", 15: "Duck", 17: "Yak",
        18: "Camels", 19: "Emus", 21: "Deer", 22: "Geese", 23: "Bees",
        25: "Alligators", 26: "Guinea Fowl", 27: "Musk Ox", 28: "Ostriches",
        29: "Pheasants", 30: "Pigeons", 31: "Quails", 33: "Snails", 34: "Buffalo"
    }

    Animals = []
    for A, S, P in Results:
        Price = float(P.Price) if P and P.Price else 0
        StudFee = float(P.StudFee) if P and P.StudFee else 0
        SalePrice = float(P.SalePrice) if P and P.SalePrice else 0

        Animals.append({
            "AnimalID": A.AnimalID,
            "FullName": A.FullName,
            "SpeciesID": A.SpeciesID,
            "SpeciesName": SpeciesMap.get(A.SpeciesID, "Unknown"),
            "Price": Price,
            "StudFee": StudFee,
            "SalePrice": SalePrice,
            "PublishForSale": A.PublishForSale,
        })

    return Animals