"""D4: map_pending validates, caps, and dedupes viz specs (no LLM)."""
from __future__ import annotations

import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("REDIS_ALLOW_MEMORY_FALLBACK", "true")

from visualizations.mapper import (
    MAX_CALENDAR_EVENTS,
    MAX_SERIES_POINTS,
    MAX_SPECS,
    MAX_TABLE_ROWS,
    map_pending,
)


def _alert(i: int, title: str | None = None) -> dict:
    return {
        "id": f"alert_{i}",
        "type": "alert_card",
        "title": title or f"Alert {i}",
        "source_tool": "get_field_alerts_tool",
        "data": {
            "severity": "high",
            "message": f"Heat stress {i}",
            "field_name": "North 40",
        },
    }


def _kpi(value=28, title="Water deficit") -> dict:
    return {
        "id": "kpi_1",
        "type": "kpi",
        "title": title,
        "data": {"value": value, "unit": "in"},
    }


def test_empty_in_empty_out():
    assert map_pending(None) == []
    assert map_pending([]) == []
    assert map_pending(()) == []


def test_bad_spec_dropped():
    good = _kpi()
    out = map_pending(
        [
            {"id": "x", "type": "sankey", "title": "Flows", "data": {"value": 1}},
            {"id": "line", "type": "line_chart", "title": "NDVI", "data": {"series": []}},
            {"id": "kpi_bad", "type": "kpi", "title": "Empty", "data": {"unit": "in"}},
            "not a dict",
            good,
        ]
    )
    assert len(out) == 1
    assert out[0]["type"] == "kpi"
    assert out[0]["data"]["value"] == 28


def test_five_alerts_cap_three():
    raw = [_alert(i) for i in range(5)]
    out = map_pending(raw)
    assert len(out) == MAX_SPECS == 3
    assert [s["title"] for s in out] == ["Alert 0", "Alert 1", "Alert 2"]
    assert all(s["type"] == "alert_card" for s in out)


def test_dedupe_by_type_and_title():
    out = map_pending(
        [
            _alert(1, title="Heat stress"),
            _alert(2, title="Heat stress"),
            _kpi(title="Water deficit"),
            _kpi(value=0.5, title="Water deficit"),
        ]
    )
    assert [(s["type"], s["title"]) for s in out] == [
        ("alert_card", "Heat stress"),
        ("kpi", "Water deficit"),
    ]
    assert out[0]["id"] == "alert_1"
    assert out[1]["data"]["value"] == 28


def test_series_capped_at_90():
    series = [{"date": f"d{i}", "value": i} for i in range(1, 101)]
    out = map_pending(
        [
            {
                "id": "line",
                "type": "line_chart",
                "title": "NDVI",
                "data": {"xKey": "date", "yKey": "value", "series": series},
            }
        ]
    )
    assert len(out) == 1
    kept = out[0]["data"]["series"]
    assert len(kept) == MAX_SERIES_POINTS
    assert kept[0]["value"] == 11
    assert kept[-1]["value"] == 100


def test_table_rows_capped_at_50():
    rows = [[f"animal_{i}", "F", "2022-01-01", "for-sale"] for i in range(60)]
    out = map_pending(
        [
            {
                "id": "tbl",
                "type": "table",
                "title": "Livestock inventory",
                "data": {"columns": ["Name", "Sex", "DOB", "Status"], "rows": rows},
            }
        ]
    )
    assert len(out[0]["data"]["rows"]) == MAX_TABLE_ROWS
    assert out[0]["data"]["rows"][0][0] == "animal_0"
    assert out[0]["data"]["rows"][-1][0] == "animal_49"


def test_calendar_events_capped_at_50():
    events = [
        {"date": f"2026-04-{(i % 28) + 1:02d}", "kind": "activity", "label": f"Op {i}"}
        for i in range(60)
    ]
    out = map_pending(
        [
            {
                "id": "cal",
                "type": "calendar",
                "title": "Field calendar",
                "data": {"year": 2026, "month": 4, "events": events},
            }
        ]
    )
    assert len(out[0]["data"]["events"]) == MAX_CALENDAR_EVENTS
    assert out[0]["data"]["events"][0]["label"] == "Op 0"
    assert out[0]["data"]["events"][-1]["label"] == "Op 49"
