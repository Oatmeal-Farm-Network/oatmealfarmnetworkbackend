import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# Prevent module import connection attempts
mock_db_session = MagicMock()
with patch("app.database.SessionLocal") as mock_session_local:
    mock_session_local.return_value.__enter__.return_value = mock_db_session
    from app.main import app
    from app.database import get_db

@pytest.mark.smoke
def test_smoke_endpoints_registered():  # Removed 'app' from parentheses
    for route in app.routes:
        if hasattr(route, 'path'):  # Only access path if it exists
            # Your existing verification logic here
            assert route.path.startswith("/")

@pytest.mark.smoke
def test_smoke_get_testimonial_requests():
    """Smoke test for GET /api/events/{event_id}/testimonial-requests happy path with mock DB."""
    mock_db = MagicMock()
    # Mocking basic list return
    class MockRow:
        def __init__(self, data):
            self._mapping = data
    mock_db.execute.return_value.fetchall.return_value = [
        MockRow({"RowID": 1, "Email": "smoke@example.com", "Name": "Smoke Test", "SentDate": "2026-07-07", "Status": "sent"})
    ]
    
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    
    response = client.get("/api/events/1/testimonial-requests")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["Email"] == "smoke@example.com"
    
    app.dependency_overrides.clear()
