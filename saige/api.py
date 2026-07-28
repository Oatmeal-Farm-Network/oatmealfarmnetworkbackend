# Compatibility shim — ASGI entry for ``uvicorn api:app`` and server_all.py
from app.api import app
from app.lifecycle import app_lifespan

__all__ = ["app", "app_lifespan"]
