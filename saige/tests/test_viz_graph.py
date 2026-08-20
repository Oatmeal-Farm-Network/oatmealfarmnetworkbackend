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
    synthesizer_node,
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
            "proposals": [],
        }
    )
    assert out["visualizations"] == []


def test_synthesizer_concat_caps_alerts():
    out = synthesizer_node(
        {
            "user_message": "Any field alerts?",
            "history": ["User: Any field alerts?"],
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
        }
    )
    assert len(out) == 2


def test_joke_route_clears_visualizations(monkeypatch):
    monkeypatch.setattr(
        "graph.nodes.joke_node",
        lambda state: {"diagnosis": "ha", "recommendations": []},
    )
    out = joke_route_node({"user_message": "tell me a joke", "history": []})
    assert out["visualizations"] == []
    assert out["advisory_type"] == "joke"


def test_synthesizer_prompt_forbids_ascii_charts():
    src = inspect.getsource(synthesizer_node)
    assert "If charts will be shown, describe them in one sentence." in src
    assert "Do not paste tables of numbers or ASCII charts." in src
