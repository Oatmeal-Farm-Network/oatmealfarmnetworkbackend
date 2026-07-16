"""Smoke tests for the precision_ag router registered on the FastAPI app."""

from __future__ import annotations

import importlib
import json as _json
import re as _re
import sys
import types
import uuid as _uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.database import get_db


def _noop(*args, **kwargs):
    return None


def _identity(value=None, *args, **kwargs):
    return value


def _stub_module(module_name: str, exports: dict[str, object] | None = None) -> types.ModuleType:
    module = types.ModuleType(module_name)
    if exports:
        for export_name, export_value in exports.items():
            setattr(module, export_name, export_value)

    def __getattr__(name: str):
        if name == "router" or name.endswith("router") or name.endswith("ROUTER"):
            return APIRouter()
        if name in {"SENDGRID_API_KEY", "SENDGRID_URL", "FROM_EMAIL"}:
            return ""
        if name.isupper() or name.endswith("_URL") or name.endswith("_KEY"):
            return ""
        return _noop

    module.__getattr__ = __getattr__  # type: ignore[attr-defined]
    return module


def _install_import_shims() -> dict[str, object | None]:
    import app

    app.json = _json
    app.re = _re
    app.uuid = _uuid

    routers_package = sys.modules.get("routers")
    if routers_package is None:
        routers_package = types.ModuleType("routers")
        routers_package.__path__ = []  # type: ignore[attr-defined]
        sys.modules["routers"] = routers_package

    router_stubs = {
        "routers.translation": {"translate_fields": _identity, "translate_list": _identity},
        "routers.rbac": {"record_audit": _noop},
        "routers.notifications": {
            "notify_business": _noop,
            "create_notification": _noop,
            "_push_to_person": _noop,
        },
        "routers.platform_settings": {"get_stripe_config": _identity},
        "routers.services": {
            "SENDGRID_API_KEY": "",
            "SENDGRID_URL": "",
            "FROM_EMAIL": "",
        },
        "routers.esci": {"_ensure_tables": _noop},
        "routers.esg_reports": {"_live_metrics": _identity, "_manual_metrics": _identity},
        "routers.outgrower": {"_auto_settle_to_accounting": _noop},
        "routers.procurement": {"_sync_po_to_accounting_bill": _noop},
        "routers.event_promo_codes": {
            "compute_discount": _identity,
            "_validate_promo": _identity,
            "_normalize_code": _identity,
        },
        "routers.animals": {},
        "routers.ranches": {},
    }

    for module_name, exports in router_stubs.items():
        module = sys.modules.get(module_name)
        if module is None:
            module = _stub_module(module_name, exports)
            sys.modules[module_name] = module
        else:
            for export_name, export_value in exports.items():
                setattr(module, export_name, export_value)
        setattr(routers_package, module_name.split(".", 1)[1], module)

    repo_root = Path(__file__).resolve().parents[2]
    router_directory = repo_root / "app" / "routers"
    for path in router_directory.glob("*.py"):
        module_stem = path.stem
        if module_stem in {
            "__init__",
            "precision_ag",
            "land_leasing",
            "food_wanted",
            "livestock_knowledgebase",
        }:
            continue
        module_name = f"app.routers.{module_stem}"
        sys.modules[module_name] = _stub_module(module_name)

    service_module_name = "app.services.marketplace_stripe"
    sys.modules[service_module_name] = _stub_module(service_module_name)

    return {}


class _FakeResult:
    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def mappings(self):
        return self

    def all(self):
        return []

    def scalar(self):
        return 0


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def first(self):
        return None

    def all(self):
        return []


class _FakeSession:
    def execute(self, *args, **kwargs):
        return _FakeResult()

    def query(self, *args, **kwargs):
        return _FakeQuery()

    def add(self, *args, **kwargs):
        return None

    def delete(self, *args, **kwargs):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def refresh(self, *args, **kwargs):
        return None

    def close(self):
        return None


def _path_for_openapi_parameter(path: str) -> str:
    replacements = {
        "{field_id}": "1",
        "{listing_id}": "1",
        "{ad_id}": "1",
        "{response_id}": "1",
        "{business_id}": "1",
        "{uuid}": str(_uuid.UUID(int=0)),
        "{path}": "sample-path",
    }
    for token, replacement in replacements.items():
        path = path.replace(token, replacement)
    return path


def _load_precision_app() -> FastAPI:
    _install_import_shims()

    database_module = importlib.import_module("app.database")
    sys.modules.setdefault("database", database_module)
    sys.modules.setdefault("dependencies", importlib.import_module("app.dependencies"))
    sys.modules.pop("app.routers.precision_ag", None)
    precision_module = importlib.import_module("app.routers.precision_ag")
    setattr(importlib.import_module("app.routers"), "precision_ag", precision_module)
    sys.modules.pop("app.main", None)
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = MagicMock()
    mock_engine.begin.return_value.__exit__.return_value = None
    mock_engine.connect.return_value.__enter__.return_value = MagicMock()
    mock_engine.connect.return_value.__exit__.return_value = None
    mock_engine.execute.return_value = _FakeResult()

    patcher = patch.object(database_module, "engine", mock_engine)
    patcher.start()
    try:
        main_module = importlib.import_module("app.main")
    finally:
        patcher.stop()

    main_module.app.dependency_overrides[get_db] = _FakeSession
    return main_module.app


def test_precision_ag_smoke():
    """Verify every registered GET route under precision_ag stays below HTTP 500."""
    app = _load_precision_app()
    client = TestClient(app)
    precision_path_prefixes = ("/api/fields", "/api/precision-ag")
    openapi_paths = app.openapi().get("paths", {})

    precision_routes = [
        path
        for path, methods in openapi_paths.items()
        if path.startswith(precision_path_prefixes) and "get" in methods
    ]

    assert precision_routes, "No precision_ag GET routes were registered on app.main:app"

    for path in precision_routes:
        response = client.get(_path_for_openapi_parameter(path))
        assert response.status_code != 500, (
            f"GET {path} returned 500 Internal Server Error. "
            f"Response: {response.text}"
        )
