# --- tests/test_farm_viz_intents.py ---
from __future__ import annotations

import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("REDIS_ALLOW_MEMORY_FALLBACK", "true")

from graph.farm_viz_intents import farm_viz_intent, pinned_routes
from graph.nodes import _keyword_routes, supervisor_node
from tools.agriculture.precision_ag import resolve_commodity_name
from visualizations.mapper import merge_visualizations


def test_qa_prompts_pin_routes():
    assert farm_viz_intent("Should I irrigate Alfalfa field 9?") == "irrigate"
    assert pinned_routes("Should I irrigate Alfalfa field 9?") == ["crop"]
    assert farm_viz_intent("How has Alfalfa field 9 NDVI been?") == "ndvi_history"
    assert pinned_routes("How has Alfalfa field 9 NDVI been?") == ["monitoring"]
    assert farm_viz_intent("Any field alerts?") == "field_alerts"
    assert pinned_routes("Any field alerts?") == ["monitoring"]
    assert farm_viz_intent("Show my animals") == "animals"
    assert pinned_routes("Show my animals") == ["livestock"]
    assert farm_viz_intent("What growth stage is Alfalfa field 9?") == "growth_stage"
    assert pinned_routes("What growth stage is Alfalfa field 9?") == ["crop"]
    assert farm_viz_intent("Tell me a joke") == "joke"
    assert farm_viz_intent("Hello") == "hello"
    assert farm_viz_intent("3-day forecast for Des Moines, Iowa?") is None
    assert farm_viz_intent("Which of my fields is doing best?") == "farm_benchmark"
    assert pinned_routes("Which of my fields is doing best?") == ["crop"]
    assert farm_viz_intent("how's the farm") == "farm_benchmark"
    assert farm_viz_intent("Show field activity for Alfalfa field 9") == "field_activity"
    assert pinned_routes("Show field activity for Alfalfa field 9") == ["crop"]
    assert farm_viz_intent("Show management zones for Alfalfa field 9") == "field_zones"
    assert pinned_routes("Show management zones for Alfalfa field 9") == ["monitoring"]
    assert farm_viz_intent("What's the corn price trend over the last 30 days?") == "price_trend"
    assert pinned_routes("What's the corn price trend over the last 30 days?") == ["crop"]
    assert farm_viz_intent("List my fields") == "farm_map"
    assert pinned_routes("List my fields") == ["crop"]


def test_field_alerts_not_weather():
    assert "weather" not in (pinned_routes("Any field alerts?") or [])
    assert _keyword_routes("Any field alerts?") == ["monitoring"]
    assert _keyword_routes("Should I irrigate Alfalfa field 9?") == ["crop"]
    assert _keyword_routes("Show my animals") == ["livestock"]
    assert _keyword_routes("Which of my fields is doing best?") == ["crop"]
    assert _keyword_routes("how's the farm") == ["crop"]
    assert _keyword_routes("Show field activity for Alfalfa field 9") == ["crop"]
    assert _keyword_routes("Show management zones for Alfalfa field 9") == ["monitoring"]
    assert _keyword_routes("What's the corn price trend over the last 30 days?") == ["crop"]
    assert "weather" not in _keyword_routes("how's the farm")
    assert "monitoring" not in _keyword_routes("Which of my fields is doing best?")


def test_supervisor_skips_llm_for_pinned_intents():
    out = supervisor_node({
        "user_message": "Any field alerts?",
        "history": ["User: Any field alerts?"],
        "proposals": [],
    })
    assert out["route"] == ["monitoring"]
    assert out["supervisor_reasoning"].startswith("farm-viz:")


def test_commodity_from_price_prompt():
    assert resolve_commodity_name("What's the corn price trend over the last 30 days?") == "Corn"
    assert resolve_commodity_name("soybean prices") == "Nat'l Soybeans"


def test_merge_prefers_kpi_over_farm_map():
    farm = {
        "id": "farm_map",
        "type": "farm_map",
        "title": "Farm fields",
        "data": {"field_ids": [12, 26]},
    }
    kpi = {
        "id": "kpi_1",
        "type": "kpi",
        "title": "Water deficit",
        "data": {"value": 0.4, "unit": "in"},
    }
    line = {
        "id": "line_1",
        "type": "line_chart",
        "title": "ET vs rainfall",
        "data": {
            "xKey": "date",
            "yKey": "deficit_in",
            "series": [{"date": "2026-08-01", "deficit_in": 0.1}],
        },
    }
    alert = {
        "id": "alert_1",
        "type": "alert_card",
        "title": "NO_DATA",
        "data": {"severity": "medium", "message": "cloud", "field_name": "saf"},
    }
    out = merge_visualizations([farm, alert], [kpi, line])
    assert [s["type"] for s in out] == ["kpi", "line_chart", "alert_card"]
