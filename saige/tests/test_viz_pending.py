"""D3: viz pending side-channel + tool emits (tools still return str)."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("REDIS_ALLOW_MEMORY_FALLBACK", "true")

from visualizations.pending import viz_emit, viz_reset, viz_take


def test_pending_reset_emit_take():
    viz_reset()
    assert viz_take() == []
    viz_emit({"id": "a", "type": "kpi"})
    viz_emit({"id": "b", "type": "table"})
    out = viz_take()
    assert [s["id"] for s in out] == ["a", "b"]
    assert viz_take() == []


def test_pending_emit_without_reset():
    viz_reset()
    viz_take()
    viz_emit({"id": "solo"})
    assert viz_take() == [{"id": "solo"}]


def _patch_field(monkeypatch):
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._business_ids_for_people",
        lambda *a, **k: [15627],
    )
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._field_accessible",
        lambda *a, **k: {"name": "North 40", "croptype": "corn", "businessid": 15627},
    )


def _daily_irrigation(n: int):
    rows = []
    for i in range(n):
        rows.append({
            "date": f"2026-08-{i + 1:02d}",
            "precip_in": 0.1,
            "etc_in": 0.2,
            "deficit_in": 0.1,
        })
    return rows


def test_irrigation_seven_days_emits_line_chart(monkeypatch):
    from tools.agriculture.precision_ag import get_field_irrigation_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._api_get",
        lambda path: {
            "recommendation": "Irrigate now",
            "urgency": "high",
            "cumulative_deficit_in": 0.42,
            "kc": 1.15,
            "crop_type": "corn",
            "daily": _daily_irrigation(7),
        },
    )
    viz_reset()
    text = get_field_irrigation_tool.invoke({"field_id": 12, "days": 7, "people_id": "5699"})
    assert isinstance(text, str)
    assert "0.42" in text
    specs = viz_take()
    lines = [s for s in specs if s["type"] == "line_chart"]
    assert len(lines) == 1
    assert len(lines[0]["data"]["series"]) == 7
    assert "Soil moisture" not in lines[0]["title"]
    kpis = [s for s in specs if s["type"] == "kpi"]
    assert kpis and kpis[0]["data"]["unit"] == "in"


def test_irrigation_empty_daily_no_line(monkeypatch):
    from tools.agriculture.precision_ag import get_field_irrigation_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._api_get",
        lambda path: {
            "recommendation": "No irrigation needed",
            "urgency": "low",
            "cumulative_deficit_in": 0.0,
            "kc": 1.0,
            "crop_type": "corn",
            "daily": [],
        },
    )
    viz_reset()
    text = get_field_irrigation_tool.invoke({"field_id": 12, "days": 7, "people_id": "5699"})
    assert isinstance(text, str)
    specs = viz_take()
    assert not any(s["type"] == "line_chart" for s in specs)


def test_history_ndvi_emits_line(monkeypatch):
    from tools.agriculture.precision_ag import get_field_history_tool

    _patch_field(monkeypatch)
    rows = []
    for i in range(7):
        rows.append({
            "analysisid": i + 1,
            "analysisdate": f"2026-07-{i + 1:02d}",
            "cloudpercent": 5,
            "indextype": "NDVI",
            "meanvalue": 0.40 + i * 0.01,
        })
    monkeypatch.setattr("tools.agriculture.precision_ag._query", lambda *a, **k: rows)
    viz_reset()
    text = get_field_history_tool.invoke({"field_id": 12, "months": 6, "people_id": "5699"})
    assert isinstance(text, str)
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "line_chart"
    assert len(specs[0]["data"]["series"]) == 7


def test_history_empty_query_no_viz(monkeypatch):
    from tools.agriculture.precision_ag import get_field_history_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr("tools.agriculture.precision_ag._query", lambda *a, **k: [])
    viz_reset()
    text = get_field_history_tool.invoke({"field_id": 12, "months": 6, "people_id": "5699"})
    assert "No analyses" in text
    assert viz_take() == []


def test_alerts_cap_three(monkeypatch):
    from tools.agriculture.precision_ag import get_field_alerts_tool

    _patch_field(monkeypatch)
    rows = [
        {
            "alertid": i,
            "alerttype": "stress",
            "severity": "high",
            "message": f"alert {i}",
            "status": "open",
            "createdat": "2026-08-01",
            "fieldname": "North 40",
            "fieldid": 12,
        }
        for i in range(4)
    ]
    monkeypatch.setattr("tools.agriculture.precision_ag._query", lambda *a, **k: rows)
    viz_reset()
    text = get_field_alerts_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert isinstance(text, str)
    specs = viz_take()
    assert len(specs) == 3
    assert all(s["type"] == "alert_card" for s in specs)


def test_gdd_emits_kpi(monkeypatch):
    from tools.agriculture.precision_ag import get_field_gdd_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._api_get",
        lambda path: {
            "total_gdd": 1420,
            "base_temp_f": 50,
            "crop_type": "corn",
            "daily": [{"date": "2026-08-01", "gdd": 20}],
        },
    )
    viz_reset()
    text = get_field_gdd_tool.invoke({"field_id": 12, "days": 180, "people_id": "5699"})
    assert isinstance(text, str)
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "kpi"
    assert specs[0]["data"]["value"] == 1420
    assert specs[0]["data"]["unit"] == "GDD"


def test_animals_emits_table(monkeypatch):
    from tools.farm.business_data import list_my_animals_detail_tool

    monkeypatch.setattr(
        "tools.farm.business_data._query",
        lambda *a, **k: [
            {
                "AnimalID": 1,
                "FullName": "Bella",
                "Sex": "F",
                "DOB": "2022-03-01",
                "ForSale": 1,
                "ForStud": 0,
                "Price": 1500,
                "StudPrice": None,
                "IsActive": 1,
                "ShowOnWebsite": 1,
            }
        ],
    )
    viz_reset()
    text = list_my_animals_detail_tool.invoke({"business_id": 15627})
    assert isinstance(text, str)
    assert "Bella" in text
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "table"
    assert specs[0]["data"]["rows"][0][0] == "Bella"


def test_animals_empty_no_viz(monkeypatch):
    from tools.farm.business_data import list_my_animals_detail_tool

    monkeypatch.setattr("tools.farm.business_data._query", lambda *a, **k: [])
    viz_reset()
    text = list_my_animals_detail_tool.invoke({"business_id": 15627})
    assert "No animals" in text
    assert viz_take() == []


def test_prepare_turn_resets_pending(monkeypatch):
    viz_emit({"id": "stale"})
    monkeypatch.setattr("chat.service.get_last_n", lambda *a, **k: [])
    monkeypatch.setattr("chat.service._get_state", lambda *a, **k: SimpleNamespace(next=()))
    monkeypatch.setattr("chat.service.graph", MagicMock())
    monkeypatch.setattr("chat.service.chat_history.get_user_memory", lambda *a, **k: {})
    monkeypatch.setattr("chat.service.chat_history.get_org_memory", lambda *a, **k: {})
    from chat.service import _prepare_turn

    _prepare_turn(
        user_input="hi",
        thread_id="t",
        people_id="1",
        business_id=None,
        image_data=None,
        skip_history=True,
    )
    assert viz_take() == []


def test_scouting_emits_timeline_not_heatmap(monkeypatch):
    from tools.agriculture.precision_ag import get_field_scouting_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._query",
        lambda *a, **k: [
            {
                "noteid": 1,
                "notedate": "2026-08-01",
                "category": "Pest",
                "severity": "high",
                "title": "Aphids on leaves",
                "content": "Colony on lower canopy",
                "latitude": 42.36,
                "longitude": -71.06,
                "imageurl": "https://example.com/aphid.jpg",
            },
            {
                "noteid": 2,
                "notedate": "2026-08-08",
                "category": "Disease",
                "severity": "medium",
                "title": "Leaf spot",
                "content": "",
                "latitude": None,
                "longitude": None,
                "imageurl": None,
            },
        ],
    )
    viz_reset()
    text = get_field_scouting_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert isinstance(text, str)
    assert "Aphids" in text
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "timeline"
    assert len(specs[0]["data"]["items"]) == 2
    blob = str(specs).lower()
    assert "heatmap" not in blob
    assert "geojson" not in blob


def test_scouting_empty_no_viz(monkeypatch):
    from tools.agriculture.precision_ag import get_field_scouting_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr("tools.agriculture.precision_ag._query", lambda *a, **k: [])
    viz_reset()
    text = get_field_scouting_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert "No scouting" in text
    assert viz_take() == []


def test_pest_photos_emit_alert_with_confidence(monkeypatch):
    from tools.agriculture.pest_detection import get_recent_pest_detections_tool

    monkeypatch.setattr("tools.agriculture.pest_detection._HISTORY_AVAILABLE", True)
    monkeypatch.setattr(
        "tools.agriculture.pest_detection._history",
        SimpleNamespace(list_for_user=lambda *a, **k: [
            {
                "id": "p1",
                "created_at": "2026-08-10T12:00:00",
                "payload": {
                    "diagnosis": "Corn earworm",
                    "confidence": "high",
                    "category": "pest",
                    "crop_identified": "corn",
                },
            },
            {
                "id": "p2",
                "created_at": "2026-08-08T12:00:00",
                "payload": {
                    "diagnosis": "Nitrogen deficiency",
                    "confidence": "medium",
                    "category": "deficiency",
                    "crop_identified": "corn",
                },
            },
        ]),
    )
    viz_reset()
    text = get_recent_pest_detections_tool.invoke({"limit": 3, "people_id": "5699"})
    assert isinstance(text, str)
    assert "Corn earworm" in text
    specs = viz_take()
    assert len(specs) == 2
    assert all(s["type"] == "alert_card" for s in specs)
    assert "high confidence" in specs[0]["data"]["message"]
    assert specs[0]["data"]["severity"] == "high"
    assert specs[1]["data"]["severity"] == "medium"


def test_agronomy_pest_alerts_emit_cards(monkeypatch):
    from tools.agriculture.precision_ag import get_field_agronomy_tool

    _patch_field(monkeypatch)

    def _fake_api(path):
        if "agronomy" in path:
            return {
                "pest_disease_alerts": [
                    {
                        "name": "Gray Leaf Spot",
                        "type": "disease",
                        "severity": "high",
                        "action": "Scout lower canopy; consider fungicide if wet.",
                        "why": "humid nights",
                    },
                    {
                        "name": "European Corn Borer",
                        "type": "pest",
                        "severity": "medium",
                        "action": "Check for shot-hole feeding.",
                    },
                ]
            }
        return {}

    monkeypatch.setattr("tools.agriculture.precision_ag._api_get", _fake_api)
    viz_reset()
    text = get_field_agronomy_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert isinstance(text, str)
    specs = viz_take()
    assert len(specs) == 2
    assert all(s["type"] == "alert_card" for s in specs)
    assert specs[0]["title"] == "Gray Leaf Spot"
