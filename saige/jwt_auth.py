# --- jwt_auth.py --- (JWT authentication dependency for FastAPI)
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from config import JWT_SECRET, JWT_ALGORITHM

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    """
    FastAPI dependency — verifies the Bearer JWT issued by the Oatmeal Farm Network
    auth backend and returns the PeopleID (stored as 'sub') as a string.

    Raises 401 if the token is missing, expired, or invalid.
    """
    if not JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="JWT_SECRET is not configured on the server.",
        )
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        people_id = payload.get("sub")
        if people_id is None:
            raise HTTPException(status_code=401, detail="Token missing subject (sub).")
        return str(people_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
