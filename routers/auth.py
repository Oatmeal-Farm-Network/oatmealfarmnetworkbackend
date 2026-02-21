from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from auth import create_access_token, get_current_user
import models

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(models.People).filter(
            models.People.PeopleEmail == request.email,
            models.People.PeopleActive == 1
        ).first()

        if not user or user.PeoplePassword != request.password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        token = create_access_token(data={"sub": user.PeopleID})

        return {
            "access_token": token,
            "token_type": "bearer",
            "people_id": user.PeopleID,
            "first_name": user.PeopleFirstName,
            "last_name": user.PeopleLastName,
            "access_level": user.accesslevel or 0
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
        "people_id": current_user.PeopleID,
        "first_name": current_user.PeopleFirstName,
        "last_name": current_user.PeopleLastName,
        "email": current_user.PeopleEmail,
        "access_level": current_user.accesslevel
    }