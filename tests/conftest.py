import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db


def _fake_get_db():
    db = MagicMock()
    try:
        yield db
    finally:
        pass


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _fake_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()