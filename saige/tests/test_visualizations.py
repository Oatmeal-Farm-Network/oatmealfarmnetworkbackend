"""Visualization spec catalog — parse, reject empty/unknown, round-trip mocks."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("REDIS_ALLOW_MEMORY_FALLBACK", "true")

from schemas.models import SaigeState
from schemas.visualizations import (
    TIER1_TYPES,
    VisualizationSpec,
    spec_to_dict,
    validate_spec,
)

_MOCKS_PATH = Path(__file__).resolve().parents[1] / "docs" / "viz_mocks.json"


def _mocks() -> list:
    return json.loads(_MOCKS_PATH.read_text(encoding="utf-8"))


def test_valid_kpi_parses():
    spec = validate_spec(
        {
            "id": "viz_1",
            "type": "kpi",
            "title": "Soil moisture",
            "source_tool": "get_field_irrigation_tool",
            "data": {"value": 28, "unit": "%", "delta": -4},
            "actions": [{"label": "Open field", "href": "/precision-ag/fields/12"}],
        }
    )
    assert spec is not None
    assert spec.type == "kpi"
    assert spec.data["value"] == 28
    assert spec.actions[0].href.endswith("/12")
    dumped = spec_to_dict(spec)
    assert dumped["type"] == "kpi"
    assert dumped["data"]["unit"] == "%"


def test_empty_line_series_rejected():
    assert (
        validate_spec(
            {
                "id": "viz_line",
                "type": "line_chart",
                "title": "NDVI",
                "data": {"xKey": "date", "yKey": "value", "series": []},
            }
        )
        is None
    )


def test_farm_map_without_ids_rejected():
    assert (
        validate_spec(
            {
                "id": "viz_farm",
                "type": "farm_map",
                "title": "Farm fields",
                "data": {"field_ids": []},
            }
        )
        is None
    )


def test_field_map_without_field_id_rejected():
    assert (
        validate_spec(
            {
                "id": "viz_field",
                "type": "field_map",
                "title": "NDVI map",
                "data": {"layer": "NDVI"},
            }
        )
        is None
    )


def test_calendar_without_events_rejected():
    assert (
        validate_spec(
            {
                "id": "viz_cal",
                "type": "calendar",
                "title": "Planting",
                "data": {"year": 2026, "month": 4, "events": []},
            }
        )
        is None
    )


def test_calendar_parses():
    spec = validate_spec(
        {
            "id": "viz_cal",
            "type": "calendar",
            "title": "Planting calendar — tomato",
            "source_tool": "planting_calendar_tool",
            "data": {
                "year": 2026,
                "month": 4,
                "events": [
                    {"date": "2026-04-29", "kind": "plant", "label": "Plant tomato"},
                    {"date": "2026-07-13", "kind": "harvest", "label": "Est. maturity (~75 days)"},
                ],
            },
        }
    )
    assert spec is not None
    assert spec.type == "calendar"
    assert spec.data["month"] == 4
    assert spec.data["events"][0]["kind"] == "plant"


def test_farm_and_field_map_parse():
    farm = validate_spec(
        {
            "id": "viz_farm",
            "type": "farm_map",
            "title": "Farm fields",
            "data": {"field_ids": [12, 15]},
            "actions": [{"label": "Open map", "href": "/precision-ag/analysis/maps"}],
        }
    )
    assert farm is not None
    assert farm.data["field_ids"] == [12, 15]
    field = validate_spec(
        {
            "id": "viz_field",
            "type": "field_map",
            "title": "NDVI map — North 40",
            "data": {"field_id": 12, "layer": "NDVI"},
        }
    )
    assert field is not None
    assert field.data["field_id"] == 12


def test_unknown_type_rejected():
    assert (
        validate_spec(
            {
                "id": "viz_x",
                "type": "sankey",
                "title": "Flows",
                "data": {"value": 1},
            }
        )
        is None
    )


def test_kpi_without_value_rejected():
    assert (
        validate_spec(
            {
                "id": "viz_kpi",
                "type": "kpi",
                "title": "Soil moisture",
                "data": {"unit": "%"},
            }
        )
        is None
    )


def test_empty_table_rows_rejected():
    assert (
        validate_spec(
            {
                "id": "viz_table",
                "type": "table",
                "title": "Livestock",
                "data": {"columns": ["Name"], "rows": []},
            }
        )
        is None
    )


def test_empty_bar_series_rejected():
    assert (
        validate_spec(
            {
                "id": "viz_bar",
                "type": "bar_chart",
                "title": "Yield",
                "data": {"xKey": "field", "yKey": "yield", "series": []},
            }
        )
        is None
    )


def test_non_dict_rejected():
    assert validate_spec(None) is None
    assert validate_spec("kpi") is None
    assert validate_spec([]) is None


def test_missing_required_fields_rejected():
    assert validate_spec({"type": "kpi", "data": {"value": 1}}) is None
    assert validate_spec({"id": "x", "type": "kpi", "data": {"value": 1}}) is None


def test_viz_mocks_round_trip():
    mocks = _mocks()
    types_seen = set()
    for raw in mocks:
        spec = validate_spec(raw)
        assert spec is not None, raw.get("type")
        types_seen.add(spec.type)
        again = validate_spec(spec_to_dict(spec))
        assert again is not None
        assert again.id == spec.id
    assert types_seen >= set(TIER1_TYPES)


def test_saige_state_accepts_visualizations():
    state: SaigeState = {
        "people_id": "5699",
        "visualizations": [spec_to_dict(VisualizationSpec.model_validate(_mocks()[0]))],
    }
    assert state["visualizations"][0]["type"] == "kpi"
