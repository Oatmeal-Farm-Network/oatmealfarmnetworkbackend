"""Smoke tests for the livestock_knowledgebase router."""

from __future__ import annotations

from test.SmokeTest.precision_ag_smoke import _load_precision_app, _path_for_openapi_parameter

import pytest
from fastapi.testclient import TestClient

# app.routers.livestock_knowledgebase has not been implemented/wired into app.main yet.
# Kept as xfail (not skip) so the assertion logic still runs every CI run: it will
# flip to XPASS the moment the router lands, which is our signal to drop this marker.
# TODO(livestock-knowledgebase): remove once the router is implemented and registered.
pytestmark = pytest.mark.xfail(
    reason="app.routers.livestock_knowledgebase not implemented/registered yet",
    strict=False,
)


def test_livestock_knowledgebase_smoke():
    """Verify every mounted GET route under livestock_knowledgebase stays below HTTP 500.

    Routes are discovered dynamically from the live app.openapi() path map rather than
    app.routes, because sub-routers are wrapped in _IncludedRouter containers on app.routes
    and would otherwise be invisible to a naive scan. If no matching paths are registered,
    this fails loudly instead of trivially passing on an empty route list.
    """
    app = _load_precision_app()
    client = TestClient(app)
    openapi_paths = app.openapi().get("paths", {})
    routes = [
        path
        for path, methods in openapi_paths.items()
        if path.startswith("/api/livestock-knowledgebase") and "get" in methods
    ]

    assert routes, (
        "No livestock_knowledgebase GET routes were registered on app.main:app. "
        "Expected paths under /api/livestock-knowledgebase in app.openapi()['paths']; "
        "verify app.routers.livestock_knowledgebase.router is included in app.main."
    )

    for path in routes:
        response = client.get(_path_for_openapi_parameter(path))
        assert response.status_code != 500, (
            f"GET {path} returned 500 Internal Server Error. "
            f"Response: {response.text}"
        )
