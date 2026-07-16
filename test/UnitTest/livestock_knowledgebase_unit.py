"""
Unit tests for livestock_knowledgebase module.

Fully isolated: no real database engine, no outbound network I/O, and no
TestClient/live-server dependency. Every boundary (DB engine, sockets) is
mocked so the suite runs deterministically, in-process, in well under a
second, matching the same isolation contract as the other *_unit.py suites.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    """Belt-and-suspenders guard: fail loudly if any code path under test attempts a
    real socket connection, so this suite can never accidentally depend on the network."""

    def _fail_on_connect(*args, **kwargs):
        raise AssertionError(
            "livestock_knowledgebase unit test attempted a real network/socket call"
        )

    monkeypatch.setattr("socket.socket.connect", _fail_on_connect, raising=False)


def _import_router():
    """Import app.routers.livestock_knowledgebase with the DB engine mocked out."""
    with patch("app.database.engine") as mock_engine:
        mock_connection = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_connection
        mock_engine.begin.return_value.__exit__.return_value = None
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        mock_engine.connect.return_value.__exit__.return_value = None

        from app.routers.livestock_knowledgebase import router

        return router


def test_livestock_knowledgebase_router_exists():
    """Test that the livestock_knowledgebase router is properly defined."""
    router = _import_router()

    assert router is not None
    assert hasattr(router, "routes")
    assert len(router.routes) > 0, "livestock_knowledgebase router has no routes registered"


def test_livestock_knowledgebase_router_prefix():
    """The router must be namespaced under /api/livestock-knowledgebase, matching the
    plant-knowledgebase / ingredient-knowledgebase sibling module convention."""
    router = _import_router()

    assert router.prefix == "/api/livestock-knowledgebase"


def test_livestock_knowledgebase_routes_use_db_dependency_injection():
    """Every GET endpoint must depend on get_db (via FastAPI Depends) rather than opening
    its own connection, which is what makes the router safely unit-testable/overridable."""
    from app.database import get_db

    router = _import_router()

    get_routes = [route for route in router.routes if "GET" in getattr(route, "methods", set())]
    assert get_routes, "No GET routes found on livestock_knowledgebase router"

    for route in get_routes:
        dependency_callables = [dep.call for dep in route.dependant.dependencies]
        assert get_db in dependency_callables, (
            f"Route {route.path} does not inject get_db via Depends and cannot be "
            "isolated from a live database connection in tests or production."
        )
