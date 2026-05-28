"""Compatibility shim — re-exports the two most common FastAPI dependencies."""
from database import get_db
from jwt_auth import get_current_user

__all__ = ["get_db", "get_current_user"]
