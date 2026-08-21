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


def test_animals_two_species_emits_bar(monkeypatch):
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
                "Species": "Alpaca",
            },
            {
                "AnimalID": 2,
                "FullName": "Duke",
                "Sex": "M",
                "DOB": "2021-11-12",
                "ForSale": 0,
                "ForStud": 1,
                "Price": None,
                "StudPrice": 400,
                "IsActive": 1,
                "ShowOnWebsite": 1,
                "Species": "Llama",
            },
        ],
    )
    viz_reset()
    text = list_my_animals_detail_tool.invoke({"business_id": 15627})
    assert isinstance(text, str)
    specs = viz_take()
    tables = [s for s in specs if s["type"] == "table"]
    bars = [s for s in specs if s["type"] == "bar_chart"]
    assert len(tables) == 1
    assert len(bars) == 1
    assert bars[0]["data"]["xKey"] == "species"
    assert bars[0]["data"]["yKey"] == "count"
    names = {p["species"] for p in bars[0]["data"]["series"]}
    assert names == {"Alpaca", "Llama"}


def test_price_trends_emits_line(monkeypatch):
    from tools.agriculture.precision_ag import get_price_trends_tool

    monkeypatch.setattr(
        "tools.agriculture.precision_ag._query",
        lambda *a, **k: [
            {"Commodity": "Corn", "PriceUSD": 4.10, "FetchedAt": "2026-07-01"},
            {"Commodity": "Corn", "PriceUSD": 4.25, "FetchedAt": "2026-07-15"},
            {"Commodity": "Corn", "PriceUSD": 4.40, "FetchedAt": "2026-08-01"},
        ],
    )
    viz_reset()
    text = get_price_trends_tool.invoke({"commodity": "Corn", "days": 30, "people_id": "5699"})
    assert isinstance(text, str)
    assert "4.40" in text
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "line_chart"
    assert specs[0]["data"]["yKey"] == "value"
    assert len(specs[0]["data"]["series"]) == 3


def test_price_forecast_emits_line_with_band(monkeypatch):
    from tools.finance.price_forecast import price_forecast_tool

    monkeypatch.setattr(
        "tools.finance.price_forecast.forecast",
        lambda *a, **k: {
            "status": "ok",
            "commodity": "corn",
            "unit": "$/bu",
            "recent_average": 4.25,
            "source": "test",
            "forecast": [
                {"month": "2026-09", "expected": 4.30, "low": 3.65, "high": 4.94},
                {"month": "2026-10", "expected": 4.35, "low": 3.70, "high": 5.00},
                {"month": "2026-11", "expected": 4.40, "low": 3.74, "high": 5.06},
            ],
            "confidence": "medium",
            "notes": "",
        },
    )
    viz_reset()
    text = price_forecast_tool.invoke({"commodity": "corn", "months_ahead": 3})
    assert isinstance(text, str)
    assert "Price forecast — corn" in text
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "line_chart"
    point = specs[0]["data"]["series"][0]
    assert point["value"] == 4.30
    assert point["low"] == 3.65
    assert point["high"] == 4.94


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


def _seven_day_forecast(loc="Boston, US"):
    days = []
    for i in range(7):
        days.append({
            "date": f"2026-08-{i + 1:02d}",
            "max_temp": 20 + i,
            "min_temp": 10 + i,
            "condition": "Clear",
            "rain_chance": 10 * i,
        })
    return {
        "location": loc,
        "current": {"temperature": 22, "condition": "Clear"},
        "forecast": days,
        "forecast_days": 7,
    }


def test_weather_forecast_emits_temp_and_rain_lines():
    from tools.weather.weather import emit_weather_visualizations

    viz_reset()
    emit_weather_visualizations(_seven_day_forecast())
    specs = viz_take()
    assert [s["type"] for s in specs] == ["line_chart", "line_chart"]
    assert specs[0]["data"]["yKey"] == "max_temp"
    assert specs[0]["data"]["unit"] == "°C"
    assert specs[1]["data"]["yKey"] == "rain_chance"
    assert len(specs[0]["data"]["series"]) == 7
    assert "min_temp" in specs[0]["data"]["series"][0]


def test_weather_forecast_one_day_no_chart():
    from tools.weather.weather import emit_weather_visualizations

    viz_reset()
    emit_weather_visualizations({
        "location": "Boston, US",
        "forecast": [{"date": "2026-08-01", "max_temp": 20, "rain_chance": 10}],
    })
    assert viz_take() == []


def test_weather_tool_keeps_format_for_llm_and_emits(monkeypatch):
    from tools.weather.weather import get_weather_tool

    current = {
        "location": "Boston, US",
        "temperature": 22,
        "feels_like": 21,
        "condition": "Clear",
        "humidity": 40,
        "wind_speed": 10,
        "pressure": 1012,
    }
    monkeypatch.setattr(
        "tools.weather.weather.weather_service.get_weather",
        lambda *a, **k: current,
    )
    monkeypatch.setattr(
        "tools.weather.weather.weather_service.get_forecast",
        lambda *a, **k: _seven_day_forecast(),
    )
    viz_reset()
    text = get_weather_tool.invoke({"location": "Boston"})
    assert isinstance(text, str)
    assert "Temperature: 22C" in text
    assert "Current weather conditions" in text
    specs = viz_take()
    assert len(specs) == 2
    assert all(s["type"] == "line_chart" for s in specs)
