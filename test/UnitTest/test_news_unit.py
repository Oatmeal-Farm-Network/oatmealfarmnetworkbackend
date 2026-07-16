from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import news


pytestmark = pytest.mark.unit


class BrokenNewsDb:
    def collection(self, name: str):
        raise RuntimeError("boom")


def test_serialize_removes_embeddings_formats_datetimes_and_repairs_text(monkeypatch):
    monkeypatch.setattr(news, "_ftfy_fix", lambda value: value.replace("â€™", "'"))
    published = datetime(2026, 7, 9, 9, 30, tzinfo=timezone(timedelta(hours=-4)))
    synced = datetime(2026, 7, 9, 14, 0, tzinfo=timezone.utc)

    serialized = news._serialize(
        "article-123",
        {
            "title": "USDAâ€™s outlook",
            "description": "Plain text",
            "embedding": [0.1, 0.2],
            "pubDate": published,
            "syncedAt": synced,
        },
    )

    assert serialized["id"] == "article-123"
    assert serialized["title"] == "USDA's outlook"
    assert serialized["pubDate"] == "2026-07-09T13:30:00+00:00"
    assert serialized["syncedAt"] == "2026-07-09T14:00:00+00:00"
    assert "embedding" not in serialized


def test_serialize_non_dict_payload_returns_id_only():
    assert news._serialize("bad-doc", None) == {"id": "bad-doc"}


def test_list_news_filters_sorts_limits_and_strips_embeddings(
    monkeypatch,
    fake_news_store,
):
    docs = [
        fake_news_store.Doc(
            "old",
            {
                "title": "Old",
                "category": "markets",
                "pubDate": "2026-07-08T09:00:00+00:00",
                "embedding": [1],
            },
        ),
        fake_news_store.Doc(
            "new",
            {
                "title": "New",
                "category": "markets",
                "pubDate": "2026-07-09T09:00:00+00:00",
                "embedding": [2],
            },
        ),
        fake_news_store.Doc(
            "other",
            {
                "title": "Other category",
                "category": "policy",
                "pubDate": "2026-07-10T09:00:00+00:00",
                "embedding": [3],
            },
        ),
    ]
    fake_db = fake_news_store.Db(docs)
    monkeypatch.setattr(news, "_get_db", lambda: fake_db)

    result = news.list_news(limit=2, category="markets")

    assert [article["id"] for article in result["articles"]] == ["new", "old"]
    assert all(article["category"] == "markets" for article in result["articles"])
    assert all("embedding" not in article for article in result["articles"])
    assert fake_db.collection_names == ["news_articles"]


def test_list_news_returns_empty_articles_when_firestore_query_fails(monkeypatch):
    monkeypatch.setattr(news, "_get_db", lambda: BrokenNewsDb())

    assert news.list_news()["articles"] == []


def test_get_article_returns_serialized_document(monkeypatch, fake_news_store):
    fake_db = fake_news_store.Db(
        [
            fake_news_store.Doc(
                "article-1",
                {"title": "Healthy soils", "pubDate": "2026-07-09T00:00:00+00:00"},
            )
        ]
    )
    monkeypatch.setattr(news, "_get_db", lambda: fake_db)

    article = news.get_article("article-1")

    assert article["id"] == "article-1"
    assert article["title"] == "Healthy soils"


def test_get_article_raises_503_when_store_is_unavailable(monkeypatch):
    monkeypatch.setattr(news, "_get_db", lambda: None)

    with pytest.raises(HTTPException) as exc:
        news.get_article("article-1")

    assert exc.value.status_code == 503


def test_get_article_raises_404_for_missing_document(monkeypatch, fake_news_store):
    monkeypatch.setattr(news, "_get_db", lambda: fake_news_store.Db([]))

    with pytest.raises(HTTPException) as exc:
        news.get_article("missing")

    assert exc.value.status_code == 404


def test_sync_status_reports_latest_sync_time(
    monkeypatch,
    fake_firestore_module,
    fake_news_store,
):
    synced_at = datetime(2026, 7, 9, 15, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(
        news,
        "_get_db",
        lambda: fake_news_store.Db(
            [fake_news_store.Doc("article-1", {"syncedAt": synced_at})]
        ),
    )

    assert news.sync_status() == {
        "lastSync": "2026-07-09T15:45:00+00:00",
        "available": True,
    }


def test_invalid_limit_is_rejected_before_news_store_access(monkeypatch):
    def fail_if_called():
        raise AssertionError("validation should run before database access")

    app = FastAPI()
    app.include_router(news.router)
    monkeypatch.setattr(news, "_get_db", fail_if_called)

    with TestClient(app) as client:
        response = client.get("/api/news?limit=0")

    assert response.status_code == 422
