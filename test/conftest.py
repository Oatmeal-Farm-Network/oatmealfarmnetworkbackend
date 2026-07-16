from __future__ import annotations

from pathlib import Path
import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest


def pytest_collect_file(file_path: Path, parent: pytest.Collector):
    """Collect custom *_unit.py and *_smoke.py files when pytest scans folders."""
    if file_path.suffix == ".py" and file_path.name.endswith("_unit.py"):
        return pytest.Module.from_parent(parent, path=file_path)
    return None


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list[pytest.Item]):
    """Deduplicate nodeids so custom unit collection does not double-run explicit file invocations."""
    seen: set[str] = set()
    unique_items: list[pytest.Item] = []
    for item in items:
        if item.nodeid in seen:
            continue
        seen.add(item.nodeid)
        unique_items.append(item)
    items[:] = unique_items
@dataclass
class FakeNewsDoc:
    id: str
    data: dict[str, Any] | None
    exists: bool = True

    def to_dict(self) -> dict[str, Any] | None:
        return self.data


class FakeNewsDocumentRef:
    def __init__(self, doc: FakeNewsDoc | None):
        self._doc = doc

    def get(self) -> FakeNewsDoc:
        if self._doc is None:
            return FakeNewsDoc(id="", data=None, exists=False)
        return self._doc


class FakeNewsQuery:
    def __init__(
        self,
        docs: list[FakeNewsDoc],
        filters: list[tuple[str, str, Any]] | None = None,
        limit_n: int | None = None,
        order: tuple[str, Any] | None = None,
    ):
        self._docs = docs
        self._filters = filters or []
        self._limit_n = limit_n
        self._order = order

    def where(self, field: str, op: str, value: Any) -> "FakeNewsQuery":
        return FakeNewsQuery(
            self._docs,
            filters=[*self._filters, (field, op, value)],
            limit_n=self._limit_n,
            order=self._order,
        )

    def limit(self, n: int) -> "FakeNewsQuery":
        return FakeNewsQuery(
            self._docs,
            filters=self._filters,
            limit_n=n,
            order=self._order,
        )

    def order_by(self, field: str, direction: Any = None) -> "FakeNewsQuery":
        return FakeNewsQuery(
            self._docs,
            filters=self._filters,
            limit_n=self._limit_n,
            order=(field, direction),
        )

    def get(self) -> list[FakeNewsDoc]:
        docs = list(self._docs)
        for field, op, value in self._filters:
            if op == "==":
                docs = [doc for doc in docs if (doc.data or {}).get(field) == value]
        if self._order:
            field, direction = self._order
            reverse = str(direction).upper().endswith("DESCENDING")
            docs.sort(key=lambda doc: (doc.data or {}).get(field) or "", reverse=reverse)
        if self._limit_n is not None:
            docs = docs[: self._limit_n]
        return docs


class FakeNewsCollection(FakeNewsQuery):
    def document(self, article_id: str) -> FakeNewsDocumentRef:
        for doc in self._docs:
            if doc.id == article_id:
                return FakeNewsDocumentRef(doc)
        return FakeNewsDocumentRef(None)


class FakeNewsDb:
    def __init__(self, docs: list[FakeNewsDoc]):
        self.docs = docs
        self.collection_names: list[str] = []

    def collection(self, name: str) -> FakeNewsCollection:
        self.collection_names.append(name)
        return FakeNewsCollection(self.docs)


@pytest.fixture(autouse=True)
def reset_news_router_state():
    from app.routers import news

    news._db_client = None
    news._db_init_failed = False
    yield
    news._db_client = None
    news._db_init_failed = False


@pytest.fixture
def fake_news_store():
    return types.SimpleNamespace(Db=FakeNewsDb, Doc=FakeNewsDoc)


@pytest.fixture
def fake_firestore_module(monkeypatch):
    google_mod = sys.modules.get("google") or types.ModuleType("google")
    cloud_mod = sys.modules.get("google.cloud") or types.ModuleType("google.cloud")
    firestore_mod = types.ModuleType("google.cloud.firestore")
    firestore_mod.Query = types.SimpleNamespace(DESCENDING="DESCENDING")

    setattr(google_mod, "cloud", cloud_mod)
    setattr(cloud_mod, "firestore", firestore_mod)

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", firestore_mod)
    return firestore_mod
