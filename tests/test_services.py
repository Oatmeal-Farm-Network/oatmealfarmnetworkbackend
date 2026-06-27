from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]

SERVICE_AND_UTIL_FILES = [
    ROOT / "app/services/marketplace_stripe.py",
    ROOT / "app/services/marketplace_catalog.py",
    ROOT / "app/services/event_emails.py",
    ROOT / "app/services/meeting_emails.py",
    ROOT / "app/services/image_service.py",
    ROOT / "app/utils/page_templates.py",
    ROOT / "app/utils/geo_utils.py",
]

SERVICE_ROUTER_FILES = [
    ROOT / "app/routers/marketplace.py",
    ROOT / "app/routers/stripe_payments.py",
    ROOT / "app/routers/meetings.py",
    ROOT / "app/routers/website_builder.py",
    ROOT / "app/routers/website_ai.py",
    ROOT / "app/routers/event_fiber_arts.py",
    ROOT / "app/routers/event_fleece.py",
    ROOT / "app/routers/event_spinoff.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_absent_import_lines(path: Path, banned_lines: list[str]):
    lines = {line.strip() for line in _read(path).splitlines()}
    for pattern in banned_lines:
        assert pattern not in lines, f"{path.name} still contains `{pattern}`"


class _ImportSetupDB:
    def execute(self, *args, **kwargs):
        return self

    def mappings(self):
        return self

    def first(self):
        return {"c": 1}

    def commit(self):
        return None


class _SessionLocalStub:
    def __call__(self):
        return self

    def __enter__(self):
        return _ImportSetupDB()

    def __exit__(self, exc_type, exc, tb):
        return False


class _ScalarResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _RouteDB:
    def __init__(self):
        self.updated = False
        self.committed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM OFNEventRegistrationCart" in sql:
            return _ScalarResult(
                {
                    "CartID": 7,
                    "EventID": 11,
                    "PeopleID": 29,
                    "Total": 24.5,
                    "Status": "pending_payment",
                    "AttendeeEmail": "dev3@example.com",
                    "AttendeeFirstName": "Dev",
                    "AttendeeLastName": "Three",
                    "StripePaymentIntentID": None,
                }
            )
        if "UPDATE OFNEventRegistrationCart" in sql:
            self.updated = True
            return _ScalarResult(None)
        raise AssertionError(f"Unexpected SQL in test double: {sql}")

    def commit(self):
        self.committed = True


def _import_with_stubbed_sessionlocal(module_name: str):
    import app.database as database_module

    original = database_module.SessionLocal
    fake_jwt = ModuleType("app.core.jwt_auth")
    fake_jwt.get_current_user = lambda: "29"
    database_module.SessionLocal = _SessionLocalStub()
    try:
        for stale in [
            module_name,
            "app.routers.platform_settings",
            "app.core.jwt_auth",
        ]:
            sys.modules.pop(stale, None)
        sys.modules["app.core.jwt_auth"] = fake_jwt
        return importlib.import_module(module_name)
    finally:
        database_module.SessionLocal = original
        sys.modules.pop("app.core.jwt_auth", None)


def test_service_and_util_sources_use_app_namespaced_imports():
    banned = [
        "from database import",
        "from models import",
        "import models",
        "from jwt_auth import",
        "from page_templates import",
        "from geo_utils import",
        "from image_service import",
        "from event_emails import",
        "from meeting_emails import",
        "from marketplace_catalog import",
        "from marketplace_stripe import",
    ]

    for path in SERVICE_AND_UTIL_FILES:
        _assert_absent_import_lines(path, banned)


def test_service_router_sources_use_app_namespaced_imports():
    banned = [
        "from database import",
        "from models import",
        "import models",
        "from jwt_auth import",
        "from auth import",
    ]

    for path in SERVICE_ROUTER_FILES:
        _assert_absent_import_lines(path, banned)


def test_service_and_util_modules_import_for_dev3_slice():
    marketplace_stripe = _import_with_stubbed_sessionlocal("app.services.marketplace_stripe")
    marketplace_catalog = importlib.import_module("app.services.marketplace_catalog")
    event_emails = importlib.import_module("app.services.event_emails")
    image_service = importlib.import_module("app.services.image_service")
    page_templates = importlib.import_module("app.utils.page_templates")
    geo_utils = importlib.import_module("app.utils.geo_utils")

    assert hasattr(marketplace_stripe, "stripe_router")
    assert hasattr(marketplace_catalog, "marketplace_router")
    assert hasattr(event_emails, "send_registration_confirmation")
    assert hasattr(image_service, "ensure_images_for_catalog")
    assert isinstance(page_templates.PAGE_TEMPLATES, list)
    assert geo_utils.polygon_area_hectares(
        {
            "type": "Polygon",
            "coordinates": [[
                [-104.99, 39.74],
                [-104.98, 39.74],
                [-104.98, 39.75],
                [-104.99, 39.75],
                [-104.99, 39.74],
            ]],
        }
    ) > 0


def test_stripe_payment_intent_route_returns_client_secret_with_mocked_dependencies():
    stripe_payments = _import_with_stubbed_sessionlocal("app.routers.stripe_payments")
    fake_db = _RouteDB()

    app = FastAPI()
    app.include_router(stripe_payments.router)
    app.dependency_overrides[stripe_payments.get_db] = lambda: fake_db

    fake_stripe = SimpleNamespace(
        PaymentIntent=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                id="pi_dev3",
                client_secret="secret_dev3",
                status="requires_payment_method",
            )
        )
    )

    original_stripe = stripe_payments._stripe
    stripe_payments._stripe = lambda db: (
        fake_stripe,
        {"CurrencyCode": "USD", "RefundModel": "immediate_charge"},
    )
    try:
        response = TestClient(app).post("/api/events/cart/7/payment-intent")
    finally:
        stripe_payments._stripe = original_stripe
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "clientSecret": "secret_dev3",
        "paymentIntentId": "pi_dev3",
    }
    assert fake_db.updated is True
    assert fake_db.committed is True
