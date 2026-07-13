import pytest
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.dashboard import router, get_db


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDB:
    def execute(self, query, params):
        row = SimpleNamespace(
            fields=1,
            animals=2,
            pending_orders=0,
            upcoming_events=1,
            blog_posts=0,
            products=3,
            services=2,
            produce=1,
            aggregator_b2b_open=0,
            aggregator_farms=0,
        )
        return FakeResult(row)


def override_get_db():
    yield FakeDB()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.mark.smoke
def test_dashboard_smoke_app_starts(client):
    assert client is not None


@pytest.mark.smoke
def test_dashboard_summary_returns_200(client):
    response = client.get("/api/dashboard/summary?business_id=15633")
    assert response.status_code == 200


@pytest.mark.smoke
def test_dashboard_biz_summary_returns_200(client):
    response = client.get("/api/dashboard/biz-summary?business_id=15633")
    assert response.status_code == 200


@pytest.mark.smoke
def test_dashboard_summary_returns_json(client):
    response = client.get("/api/dashboard/summary?business_id=15633")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.smoke
def test_dashboard_summary_missing_business_id_returns_422(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 422