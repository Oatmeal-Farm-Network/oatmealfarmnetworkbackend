import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Mock SessionLocal to prevent real DB connections during import
mock_db_session = MagicMock()
with patch("app.database.SessionLocal") as mock_session_local, \
     patch("app.database.engine") as mock_engine:
    mock_session_local.return_value.__enter__.return_value = mock_db_session
    from app.main import app
    from app.database import get_db

# Helper Mock classes to simulate SQLAlchemy DB rows
class MockRow:
    def __init__(self, data: dict):
        self.__dict__["_data"] = data
        self.__dict__["_mapping"] = data

    def __getattr__(self, name):
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def __getitem__(self, index):
        values = list(self._data.values())
        return values[index]

class MockExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def mappings(self):
        return self

    def first(self):
        if not self._rows:
            return None
        return self._rows[0]._mapping

@pytest.mark.unit
def test_ensure_tables():
    from app.routers.event_testimonials import ensure_tables
    mock_db = MagicMock()
    ensure_tables(mock_db)
    assert mock_db.execute.call_count == 2
    assert mock_db.commit.called

@pytest.mark.unit
def test_send_testimonials_event_not_found():
    # Setup mock db
    mock_db = MagicMock()
    
    # _event_header query returns no rows
    mock_db.execute.return_value = MockExecuteResult([])
    
    # Set up dependency override
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    
    response = client.post("/api/events/999/request-testimonials")
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    
    app.dependency_overrides.clear()

@pytest.mark.unit
def test_send_testimonials_no_attendees():
    mock_db = MagicMock()
    
    # Define side effect for execute to return event header but no attendees
    def mock_execute(statement, params=None):
        sql = str(statement)
        if "OFNEvents" in sql:
            return MockExecuteResult([
                MockRow({
                    "EventID": 1,
                    "EventName": "Oatmeal Festival",
                    "EventStartDate": "2026-07-07",
                    "EventEndDate": "2026-07-08",
                    "BusinessID": 42
                })
            ])
        else:
            # Attendee queries return empty list
            return MockExecuteResult([])
            
    mock_db.execute.side_effect = mock_execute
    
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    
    response = client.post("/api/events/1/request-testimonials")
    assert response.status_code == 200
    data = response.json()
    assert data["sent"] == 0
    assert data["skipped"] == 0
    assert data["attendees"] == 0
    assert "No paid attendees" in data["message"]
    
    app.dependency_overrides.clear()

@pytest.mark.unit
def test_send_testimonials_dry_run():
    mock_db = MagicMock()
    
    # Define side effect for execute
    def mock_execute(statement, params=None):
        sql = str(statement)
        if "OFNEvents" in sql:
            return MockExecuteResult([
                MockRow({
                    "EventID": 1,
                    "EventName": "Oatmeal Festival",
                    "EventStartDate": "2026-07-07",
                    "EventEndDate": "2026-07-08",
                    "BusinessID": 42
                })
            ])
        elif "OFNEventAttendees" in sql:
            # Attendees wizard flow returns 2 candidates
            return MockExecuteResult([
                MockRow({"Email": "user1@example.com", "Name": "User One", "PeopleID": 101}),
                MockRow({"Email": "user2@example.com", "Name": "User Two", "PeopleID": 102})
            ])
        elif "OFNEventRegistrationCart" in sql:
            # Fallback registration returns 1 candidate
            return MockExecuteResult([
                MockRow({"Email": "user3@example.com", "Name": "User Three", "PeopleID": 103})
            ])
        elif "SELECT Email FROM OFNEventTestimonialRequests" in sql:
            # user1@example.com already sent
            return MockExecuteResult([
                MockRow({"Email": "user1@example.com"})
            ])
        return MockExecuteResult([])

    mock_db.execute.side_effect = mock_execute
    
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    
    response = client.post("/api/events/1/request-testimonials", json={"dry_run": True})
    assert response.status_code == 200
    data = response.json()
    assert data["sent"] == 0
    assert data["skipped"] == 1  # user1 was skipped
    assert data["attendees"] == 3  # user1, user2, user3
    assert data["would_send"] == 2  # user2, user3
    assert len(data["preview"]) == 2
    
    # Ensure no db commit or insert executed
    assert not mock_db.commit.called
    app.dependency_overrides.clear()

@pytest.mark.unit
def test_send_testimonials_success():
    mock_db = MagicMock()
    
    def mock_execute(statement, params=None):
        sql = str(statement)
        if "OFNEvents" in sql:
            return MockExecuteResult([
                MockRow({
                    "EventID": 1,
                    "EventName": "Oatmeal Festival",
                    "EventStartDate": "2026-07-07",
                    "EventEndDate": "2026-07-08",
                    "BusinessID": 42
                })
            ])
        elif "OFNEventAttendees" in sql:
            return MockExecuteResult([
                MockRow({"Email": "user1@example.com", "Name": "User One", "PeopleID": 101}),
                MockRow({"Email": "user2@example.com", "Name": "User Two", "PeopleID": 102})
            ])
        elif "OFNEventRegistrationCart" in sql:
            return MockExecuteResult([])
        elif "SELECT Email FROM OFNEventTestimonialRequests" in sql:
            # None sent yet
            return MockExecuteResult([])
        return MockExecuteResult([])

    mock_db.execute.side_effect = mock_execute
    
    # Mock send_event_testimonial_request email service function to return True
    with patch("app.services.event_emails.send_event_testimonial_request", return_value=True) as mock_send_email:
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)
        
        response = client.post("/api/events/1/request-testimonials", json={"dry_run": False})
        assert response.status_code == 200
        data = response.json()
        assert data["sent"] == 2
        assert data["skipped"] == 0
        assert data["attendees"] == 2
        
        # Verify email was sent for both candidates
        assert mock_send_email.call_count == 2
        
        # Verify db commit was called and insert statement was executed
        assert mock_db.commit.called
        # Filter execute calls to find INSERT statements
        insert_calls = [call for call in mock_db.execute.call_args_list if "INSERT INTO" in str(call[0][0])]
        assert len(insert_calls) == 2
        
    app.dependency_overrides.clear()

@pytest.mark.unit
def test_list_sent_testimonials():
    mock_db = MagicMock()
    
    mock_db.execute.return_value = MockExecuteResult([
        MockRow({
            "RowID": 1,
            "Email": "user1@example.com",
            "Name": "User One",
            "SentDate": "2026-07-07T01:00:00",
            "Status": "sent"
        }),
        MockRow({
            "RowID": 2,
            "Email": "user2@example.com",
            "Name": "User Two",
            "SentDate": "2026-07-07T02:00:00",
            "Status": "sent"
        })
    ])
    
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    
    response = client.get("/api/events/1/testimonial-requests")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["Email"] == "user1@example.com"
    assert data[1]["Email"] == "user2@example.com"
    assert data[0]["RowID"] == 1
    
    app.dependency_overrides.clear()
