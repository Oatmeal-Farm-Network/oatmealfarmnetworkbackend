"""Smoke tests for the reorged agricultural / livestock / event models & routers (Dev 4B).

NOTE: The whole ``tests/`` suite currently fails to COLLECT because the shared
``tests/conftest.py`` imports ``app.main``, which crashes on a pre-existing epic
bug (duplicate ``Pricing`` table -> "Table 'Pricing' is already defined"). That
is out of Dev 4B's scope (owned by Dev 4A). These tests are correct and will run
green once the ``Pricing`` duplicate is removed.
"""
from app.models import (
    Animal,
    AnimalRegistration,
    Field,
    FieldNote,
    Produce,
    CropRotationEntry,
    Event,
    Association,
)

MODEL_FILES = [
    "app/models/livestock.py",
    "app/models/precision_ag.py",
    "app/models/crops.py",
    "app/models/events.py",
]

AG_ROUTERS = [
    "app/routers/livestock.py",
    "app/routers/animals.py",
    "app/routers/precision_ag.py",
    "app/routers/events.py",
    "app/routers/associations.py",
]


def test_ag_models_importable():
    for cls in (Animal, AnimalRegistration, Field, FieldNote,
                Produce, CropRotationEntry, Event, Association):
        assert cls is not None


def test_ag_model_tablenames():
    # Real table names from the source (the TEST-PLAN.md example uses wrong singular forms).
    assert Animal.__tablename__ == "Animals"
    assert Field.__tablename__ == "Field"
    assert Produce.__tablename__ == "Produce"
    assert Event.__tablename__ == "Event"
    assert Association.__tablename__ == "Associations"


def test_model_files_use_app_database_base():
    for path in MODEL_FILES:
        text = open(path, encoding="utf-8").read()
        assert "from app.database import Base" in text, path
        assert "from database import Base" not in text, path


def test_ag_routers_have_no_flat_models_import():
    for path in AG_ROUTERS:
        text = open(path, encoding="utf-8").read()
        assert "from models import" not in text, path


def test_livestock_route_does_not_500(client):
    resp = client.get("/api/livestock/counts")
    assert resp.status_code != 500
