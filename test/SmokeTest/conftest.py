import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def app():
    """Provide the FastAPI app instance for testing."""
    return app

@pytest.fixture
def client():
    """Provide a TestClient for the FastAPI app."""
    return TestClient(app)
