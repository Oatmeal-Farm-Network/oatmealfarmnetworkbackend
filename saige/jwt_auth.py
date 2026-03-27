# --- jwt_auth.py --- (JWT authentication dependency for FastAPI)
import os
import httpx
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer()

AUTH_BACKEND_URL = os.getenv(
    "AUTH_BACKEND_URL",
    "https://oatmealfarmnetworkbackend-802455386518.us-central1.run.app",
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    """
    FastAPI dependency — validates the Bearer JWT by calling the auth backend's
    /auth/me endpoint. Returns the PeopleID as a string.

    Raises 401 if the token is missing, expired, or invalid.
    """
    try:
        response = httpx.get(
            f"{AUTH_BACKEND_URL}/auth/me",
            headers={"Authorization": f"Bearer {credentials.credentials}"},
            timeout=5.0,
        )
        if response.status_code == 200:
            data = response.json()
            people_id = data.get("PeopleID")
            if people_id is None:
                raise HTTPException(status_code=401, detail="Token missing PeopleID.")
            return str(people_id)
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Auth service unavailable.")
