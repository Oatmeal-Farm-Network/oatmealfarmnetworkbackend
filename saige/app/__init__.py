# Saige FastAPI application package.
#
# Prefer: ``from api import app`` (root shim) or ``uvicorn api:app``.
# Implementation: app.api / app.lifecycle / app.dependencies.
from __future__ import annotations

from typing import Any

__all__ = ["app", "app_lifespan"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from app.api import app as _app

        globals()["app"] = _app
        return _app
    if name == "app_lifespan":
        from app.lifecycle import app_lifespan as _lifespan

        globals()["app_lifespan"] = _lifespan
        return _lifespan
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
