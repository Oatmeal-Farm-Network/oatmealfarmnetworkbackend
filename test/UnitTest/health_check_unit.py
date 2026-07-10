"""Unit tests for the health-check behavior exposed by app.main."""

from test.SmokeTest.precision_ag_smoke import _load_precision_app


def test_health_check_returns_ok():
    """The health-check handler should return the expected success payload."""
    _load_precision_app()

    from app.main import health_check

    assert health_check() == {"status": "ok"}