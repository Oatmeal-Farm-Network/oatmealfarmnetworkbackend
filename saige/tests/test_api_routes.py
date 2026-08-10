"""API route presence smoke (no server)."""
from api import app


def test_critical_routes_present():
    paths = {getattr(r, "path", None) for r in app.routes}
    for p in ("/chat", "/chat/stream", "/resume", "/proposals", "/plans", "/attach", "/health"):
        assert p in paths
