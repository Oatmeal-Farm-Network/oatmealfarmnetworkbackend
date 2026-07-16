"""Smoke tests for the food_wanted router."""

from __future__ import annotations

from test.SmokeTest.precision_ag_smoke import _load_precision_app, _path_for_openapi_parameter

from fastapi.testclient import TestClient


def test_food_wanted_smoke():
    """Verify every mounted GET route under food_wanted stays below HTTP 500."""
    app = _load_precision_app()
    client = TestClient(app)
    openapi_paths = app.openapi().get("paths", {})
    routes = [
        path
        for path, methods in openapi_paths.items()
        if path.startswith("/api/food-wanted") and "get" in methods
    ]

    assert routes, "No food_wanted GET routes were registered on app.main:app"

    for path in routes:
        response = client.get(_path_for_openapi_parameter(path))
        assert response.status_code != 500, (
            f"GET {path} returned 500 Internal Server Error. "
            f"Response: {response.text}"
        )
