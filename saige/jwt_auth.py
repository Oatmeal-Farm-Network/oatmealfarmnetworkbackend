print('LOADING JWT_AUTH: ' + r'F:\Oatmeal AI\OatmealFarmNetwork Repo\Backend\oatmealfarmnetworkbackend\saige\jwt_auth.py')
# --- jwt_auth.py --- (JWT authentication dependency for FastAPI)
import os
from dotenv import load_dotenv
from jose import JWTError, jwt
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

load_dotenv()

_bearer = HTTPBearer(auto_error=False)
_bearer_optional = HTTPBearer(auto_error=False)

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    if request.method == "OPTIONS":
        return "preflight"
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Auth not configured.")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        people_id = payload.get("sub")
        if people_id is None:
            raise HTTPException(status_code=401, detail="Token missing PeopleID.")
        return str(people_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(_bearer_optional),
) -> str | None:
    if request.method == "OPTIONS":
        return None
    if not credentials or not SECRET_KEY:
        return None
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_sub": False},
        )
        people_id = payload.get("sub")
        return str(people_id) if people_id else None
    except JWTError:
        return None

def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(_bearer_optional),
) -> str | None:
    if request.method == "OPTIONS":
        return None
    if not credentials or not SECRET_KEY:
        return None
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_sub": False},
        )
        people_id = payload.get("sub")
        return str(people_id) if people_id else None
    except JWTError:
        return None