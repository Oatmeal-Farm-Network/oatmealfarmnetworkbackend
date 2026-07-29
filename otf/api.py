# Compatibility shim — ASGI entry for ``uvicorn api:app`` (Saige pattern)
from app.api import app

__all__ = ["app"]
