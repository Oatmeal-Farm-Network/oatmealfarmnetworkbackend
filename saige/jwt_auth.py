print('LOADING JWT_AUTH: ' + r'F:\Oatmeal AI\OatmealFarmNetwork Repo\Backend\oatmealfarmnetworkbackend\saige\jwt_auth.py')
# --- jwt_auth.py --- (JWT authentication dependency for FastAPI)
import os
from jose import JWTError, jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    """
    FastAPI dependency — validates the Bearer JWT locally using the shared
    SECRET_KEY. Returns the PeopleID as a string.

    Raises 401 if the token is missing, expired, or invalid.
    """
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

