from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import news


pytestmark = pytest.mark.smoke


def _client_for(fake_db, monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(news.router)
    monkeypatch.setattr(news, "_get_db", lambda: fake_db)
    return TestClient(app)


def test_news_service_starts_and_core_endpoints_return_200(
    monkeypatch,
    fake_firestore_module,
    fake_news_store,
):
    fake_db = fake_news_store.Db(
        [
            fake_news_store.Doc(
                id="article-1",
                data={
                    "title": "Market update",
                    "category": "markets",
                    "pubDate": "2026-07-09T12:00:00+00:00",
                    "syncedAt": datetime(2026, 7, 9, 12, 5, tzinfo=timezone.utc),
                },
            )
        ]
    )

    with _client_for(fake_db, monkeypatch) as client:
        feed_response = client.get("/api/news?limit=10")
        status_response = client.get("/api/news/sync/status")
        article_response = client.get("/api/news/article-1")

    assert feed_response.status_code == 200
    assert status_response.status_code == 200
    assert article_response.status_code == 200
    assert feed_response.json()["articles"][0]["id"] == "article-1"
    assert status_response.json()["available"] is True
    assert article_response.json()["title"] == "Market update"


def test_news_feed_degrades_to_empty_200_when_store_is_unavailable(monkeypatch):
    app = FastAPI()
    app.include_router(news.router)
    monkeypatch.setattr(news, "_get_db", lambda: None)

    with TestClient(app) as client:
        response = client.get("/api/news")

    assert response.status_code == 200
    assert response.json() == {"articles": []}
