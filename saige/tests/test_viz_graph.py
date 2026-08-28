"""D5: specialist packets and synthesizer attach mapped visualizations."""
from __future__ import annotations

import inspect
import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("REDIS_ALLOW_MEMORY_FALLBACK", "true")

from graph.nodes import (
    _packet_from_advisory,
    _visualizations_for_turn,
    joke_route_node,
    specialist_dispatch_node,
    synthesizer_node,
    weather_advisory_node,
)
from visualizations.mapper import drain_pending, merge_visualizations
from visualizations.pending import viz_emit, viz_reset


def _kpi(i: int, title: str | None = None) -> dict:
    return {
        "id": f"kpi_{i}",
        "type": "kpi",
        "title": title or f"Water deficit {i}",
        "data": {"value": i, "unit": "in"},
    }


def _alert(i: int) -> dict:
    return {
        "id": f"alert_{i}",
        "type": "alert_card",
        "title": f"Alert {i}",
        "data": {"severity": "high", "message": f"msg {i}", "field_name": "North 40"},
    }


def test_packet_from_advisory_copies_visualizations():
    spec = _kpi(1, "Water deficit — North 40")
    pkt = _packet_from_advisory(
        {"diagnosis": "Irrigate soon.", "recommendations": [], "visualizations": [spec]},
        "crop",
    )
    assert pkt["source"] == "crop"
    assert pkt["visualizations"] == [spec]


def test_drain_pending_maps_emits():
    viz_reset()
    viz_emit(_kpi(1))
    out = drain_pending()
    assert len(out) == 1
    assert out[0]["type"] == "kpi"
    assert drain_pending() == []


def test_merge_visualizations_caps_three():
    out = merge_visualizations([_alert(i) for i in range(3)], [_alert(i) for i in range(3, 5)])
    assert len(out) == 3
    assert [s["title"] for s in out] == ["Alert 0", "Alert 1", "Alert 2"]


def test_synthesizer_passes_irrigation_kpi():
    spec = _kpi(42, "Water deficit — North 40")
    out = synthesizer_node(
        {
            "user_message": "Should I irrigate North 40?",
            "history": ["User: Should I irrigate North 40?"],
            "route": ["crop"],
            "crop_packet": {
                "source": "crop",
                "text": "North 40 has a 0.42 in water deficit. Irrigate soon.",
                "recommendations": [],
                "visualizations": [spec],
            },
            "proposals": [],
        }
    )
    assert out["visualizations"][0]["type"] == "kpi"
    assert out["visualizations"][0]["data"]["value"] == 42


def test_synthesizer_animals_table():
    table = {
        "id": "animals_table_1",
        "type": "table",
        "title": "Livestock inventory",
        "data": {"columns": ["Name"], "rows": [["Bella"]]},
    }
    out = synthesizer_node(
        {
            "user_message": "List my animals",
            "history": ["User: List my animals"],
            "route": ["livestock"],
            "livestock_packet": {
                "source": "livestock",
                "text": "You have 1 animal on file.",
                "visualizations": [table],
            },
            "proposals": [],
        }
    )
    assert out["visualizations"][0]["type"] == "table"


def test_synthesizer_joke_no_visualizations():
    out = synthesizer_node(
        {
            "joke_text": "Why did the scarecrow win an award? Outstanding in his field.",
            "user_message": "tell me a joke",
            "history": ["User: tell me a joke"],
            "proposals": [],
        }
    )
    assert out["visualizations"] == []


def test_synthesizer_hello_no_visualizations():
    out = synthesizer_node(
        {
            "user_message": "Hello",
            "history": ["User: Hello"],
            "route": ["user"],
            "proposals": [],
        }
    )
    assert out["visualizations"] == []
    assert "I'm Saige" in (out["diagnosis"] or "")


def test_synthesizer_hello_ignores_stale_specialist_packets():
    """G12: leftover weather/livestock/monitoring from earlier turns must not bleed into Hello."""
    stale_kpi = _kpi(9, "Forecast high — Boston")
    out = synthesizer_node(
        {
            "user_message": "Hello",
            "history": ["User: Hello"],
            "route": ["user"],
            "weather_packet": {
                "source": "weather",
                "text": "High today is 91F with a frost risk tonight.",
                "visualizations": [stale_kpi],
            },
            "livestock_packet": {
                "source": "livestock",
                "text": "Herd has 12 cattle on file.",
            },
            "monitoring_packet": {
                "source": "monitoring",
                "text": "NDVI dropped on North 40.",
            },
            "proposals": [],
        }
    )
    diagnosis = out["diagnosis"] or ""
    assert "91F" not in diagnosis
    assert "cattle" not in diagnosis.lower()
    assert "NDVI" not in diagnosis
    assert out["visualizations"] == []
    assert "I'm Saige" in diagnosis


def test_specialist_dispatch_clears_stale_packets_on_user_route():
    out = specialist_dispatch_node(
        {
            "user_message": "Hello",
            "history": ["User: Hello"],
            "route": ["user"],
            "weather_packet": {
                "source": "weather",
                "text": "High today is 91F.",
                "visualizations": [_kpi(1)],
            },
            "livestock_packet": {"source": "livestock", "text": "12 cattle."},
            "monitoring_packet": {"source": "monitoring", "text": "NDVI dropped."},
        }
    )
    assert out["weather_packet"] is None
    assert out["livestock_packet"] is None
    assert out["monitoring_packet"] is None
    assert out["crop_packet"] is None
    assert out.get("visualizations") in ([], None)
    assert out.get("specialist_ms") is not None


def test_synthesizer_concat_caps_alerts():
    out = synthesizer_node(
        {
            "user_message": "Any field alerts?",
            "history": ["User: Any field alerts?"],
            "route": ["crop", "monitoring"],
            "crop_packet": {
                "source": "crop",
                "text": "Several alerts.",
                "visualizations": [_alert(i) for i in range(3)],
            },
            "monitoring_packet": {
                "source": "monitoring",
                "text": "More alerts.",
                "visualizations": [_alert(i) for i in range(3, 5)],
            },
            "proposals": [],
        }
    )
    assert len(out["visualizations"]) == 3


def test_visualizations_for_turn_uses_state_and_packets():
    spec = _kpi(1, "Growing degree days")
    out = _visualizations_for_turn(
        {
            "visualizations": [spec],
            "crop_packet": {"visualizations": [_kpi(2, "Water deficit")]},
            "route": ["crop"],
        }
    )
    assert len(out) == 2


def test_joke_route_clears_visualizations(monkeypatch):
    monkeypatch.setattr(
        "graph.nodes.joke_node",
        lambda state: {"diagnosis": "ha", "recommendations": []},
    )
    out = joke_route_node({
        "user_message": "tell me a joke",
        "history": [],
        "weather_packet": {"source": "weather", "text": "stale forecast"},
    })
    assert out["visualizations"] == []
    assert out["advisory_type"] == "joke"
    assert out["joke_text"]
    assert out["weather_packet"] is None
    assert out["livestock_packet"] is None


def test_weather_advisory_forecast_returns_line_charts(monkeypatch):
    days = [
        {
            "date": f"2026-08-{i + 1:02d}",
            "max_temp": 20 + i,
            "min_temp": 10 + i,
            "condition": "Clear",
            "rain_chance": 10 * i,
        }
        for i in range(7)
    ]
    forecast = {
        "location": "Boston, US",
        "current": {"temperature": 22, "condition": "Clear"},
        "forecast": days,
        "forecast_days": 7,
    }
    monkeypatch.setattr(
        "graph.nodes.weather_service.resolve_location",
        lambda *a, **k: {
            "status": "resolved",
            "canonical_location": "Boston, US",
            "lat": 42.36,
            "lon": -71.06,
            "confidence": 1.0,
        },
    )
    monkeypatch.setattr("graph.nodes.weather_service.get_forecast", lambda *a, **k: forecast)
    viz_reset()
    out = weather_advisory_node({
        "location": "Boston",
        "current_issues": ["7 day forecast for Boston"],
        "assessment_summary": "[forecast:7days] weather in Boston",
        "history": ["User: 7 day forecast for Boston"],
    })
    assert "Weather forecast for Boston" in out["diagnosis"]
    charts = [s for s in out["visualizations"] if s["type"] == "line_chart"]
    assert len(charts) == 2
    assert charts[0]["data"]["yKey"] == "max_temp"
    assert charts[1]["data"]["yKey"] == "rain_chance"
    pkt = _packet_from_advisory(out, "weather")
    assert len(pkt["visualizations"]) == 2


def test_synthesizer_prompt_forbids_ascii_charts():
    src = inspect.getsource(synthesizer_node)
    assert "If charts will be shown, describe them in one sentence." in src
    assert "Do not paste tables of numbers or ASCII charts." in src
