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


def _ndvi_history_rows(start: float, n: int = 3):
    rows = []
    for i in range(n):
        rows.append({
            "analysisid": i + 1,
            "analysisdate": f"2026-07-{i + 1:02d}",
            "cloudpercent": 5,
            "indextype": "NDVI",
            "meanvalue": start + i * 0.03,
        })
    return rows


def _patch_two_fields(monkeypatch):
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._business_ids_for_people",
        lambda *a, **k: [15627],
    )

    def _access(field_id, *a, **k):
        fid = int(field_id)
        if fid == 12:
            return {"name": "North 40", "croptype": "corn", "businessid": 15627}
        if fid == 15:
            return {"name": "West 20", "croptype": "soy", "businessid": 15627}
        return None

    monkeypatch.setattr("tools.agriculture.precision_ag._field_accessible", _access)


def test_compare_two_fields_emits_kpi_and_two_lines(monkeypatch):
    from tools.agriculture.precision_ag import compare_two_fields_tool

    _patch_two_fields(monkeypatch)

    def _fake_query(sql, params=()):
        fid = int(params[0]) if params else 0
        if fid == 12:
            return _ndvi_history_rows(0.50)
        if fid == 15:
            return _ndvi_history_rows(0.42)
        return []

    monkeypatch.setattr("tools.agriculture.precision_ag._query", _fake_query)
    viz_reset()
    text = compare_two_fields_tool.invoke({
        "field_id_a": 12,
        "field_id_b": 15,
        "months": 6,
        "people_id": "5699",
    })
    assert isinstance(text, str)
    assert "North 40" in text
    assert "West 20" in text
    specs = viz_take()
    assert [s["type"] for s in specs] == ["kpi", "line_chart", "line_chart"]
    kpi = specs[0]
    assert kpi["title"] == "NDVI — North 40 vs West 20"
    assert kpi["data"]["value"] == 0.56
    assert kpi["data"]["delta"] == 0.08
    assert kpi["data"]["unit"] == ""
    assert "North 40" in kpi["data"]["hint"]
    assert "West 20" in kpi["data"]["hint"]
    assert specs[1]["title"] == "NDVI — North 40"
    assert specs[2]["title"] == "NDVI — West 20"
    assert len(specs[1]["data"]["series"]) == 3
    assert len(specs[2]["data"]["series"]) == 3


def test_compare_same_field_no_viz(monkeypatch):
    from tools.agriculture.precision_ag import compare_two_fields_tool

    _patch_two_fields(monkeypatch)
    viz_reset()
    text = compare_two_fields_tool.invoke({
        "field_id_a": 12,
        "field_id_b": 12,
        "people_id": "5699",
    })
    assert "two different fields" in text.lower()
    assert viz_take() == []


def test_compare_empty_analyses_no_viz(monkeypatch):
    from tools.agriculture.precision_ag import compare_two_fields_tool

    _patch_two_fields(monkeypatch)
    monkeypatch.setattr("tools.agriculture.precision_ag._query", lambda *a, **k: [])
    viz_reset()
    text = compare_two_fields_tool.invoke({
        "field_id_a": 12,
        "field_id_b": 15,
        "people_id": "5699",
    })
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


def test_scouting_with_latlon_emits_geo_heatmap(monkeypatch):
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
    assert [s["type"] for s in specs] == ["timeline", "heatmap"]
    assert len(specs[0]["data"]["items"]) == 2
    heat = specs[1]
    assert heat["data"]["kind"] == "geo"
    assert heat["data"]["points"] == [
        {"lat": 42.36, "lon": -71.06, "label": "Aphids on leaves", "weight": 3},
    ]
    blob = str(specs).lower()
    assert "geojson" not in blob
    assert "raster" not in blob


def test_scouting_without_latlon_no_heatmap(monkeypatch):
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
    specs = viz_take()
    assert [s["type"] for s in specs] == ["timeline"]
    assert "heatmap" not in str(specs).lower()


def test_list_fields_emits_farm_map(monkeypatch):
    from tools.agriculture.precision_ag import list_my_fields_tool

    monkeypatch.setattr(
        "tools.agriculture.precision_ag._business_ids_for_people",
        lambda *a, **k: [15627],
    )
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._fields_for_people",
        lambda *a, **k: [
            {
                "fieldid": 12,
                "name": "North 40",
                "croptype": "corn",
                "fieldsizehectares": 10,
                "plantingdate": "2026-04-01",
                "monitoringenabled": 1,
                "address": "",
            },
            {
                "fieldid": 15,
                "name": "West 20",
                "croptype": "soy",
                "fieldsizehectares": 8,
                "plantingdate": "2026-04-10",
                "monitoringenabled": 1,
                "address": "",
            },
        ],
    )
    viz_reset()
    text = list_my_fields_tool.invoke({"people_id": "5699"})
    assert isinstance(text, str)
    assert "North 40" in text
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "farm_map"
    assert specs[0]["data"]["field_ids"] == [12, 15]
    assert "geojson" not in str(specs[0]).lower()


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


def test_field_analysis_emits_field_map(monkeypatch):
    from tools.agriculture.precision_ag import get_field_analysis_tool

    _patch_field(monkeypatch)

    def _fake_query(sql, params=()):
        s = sql.lower()
        if "from dbo.analysis" in s:
            return [{
                "analysisid": 99,
                "analysisdate": "2026-08-01",
                "cloudpercent": 4.0,
                "satelliteacquiredat": None,
            }]
        if "vegetationindex" in s:
            return [{
                "indextype": "NDVI",
                "meanvalue": 0.55,
                "minvalue": 0.2,
                "maxvalue": 0.8,
                "stddev": 0.1,
            }]
        return []

    monkeypatch.setattr("tools.agriculture.precision_ag._query", _fake_query)
    viz_reset()
    text = get_field_analysis_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert isinstance(text, str)
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "field_map"
    assert specs[0]["data"]["field_id"] == 12
    assert specs[0]["data"]["layer"] == "NDVI"
    assert specs[0]["data"]["analysis_id"] == 99
    assert "raster" not in str(specs[0]).lower()
    assert "geojson" not in str(specs[0]).lower()


def test_zones_emits_raster_heatmap_ids_only(monkeypatch):
    from tools.agriculture.precision_ag import get_field_zones_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._api_get",
        lambda path: {
            "zones": [
                {"zone": 0, "area_pct": 22, "mean": 0.31, "centroid": [1, 2], "pixel_count": 40},
                {"zone": 1, "area_pct": 78, "mean": 0.58, "centroid": [3, 4], "pixel_count": 140},
            ],
            "raster": {"valid_pixels": 180, "min": 0.2, "max": 0.8, "mean": 0.5},
            "image_date": "2026-08-01",
        },
    )
    viz_reset()
    text = get_field_zones_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert isinstance(text, str)
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "heatmap"
    assert specs[0]["data"]["kind"] == "raster"
    assert specs[0]["data"]["field_id"] == 12
    assert specs[0]["data"]["layer"] == "NDVI"
    blob = str(specs[0]).lower()
    assert "geojson" not in blob
    assert "valid_pixels" not in blob
    assert "centroid" not in blob


def test_zones_empty_no_viz(monkeypatch):
    from tools.agriculture.precision_ag import get_field_zones_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr("tools.agriculture.precision_ag._api_get", lambda path: {})
    viz_reset()
    text = get_field_zones_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert "No NDVI zones" in text
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


def test_planting_calendar_emits_plant_and_harvest(monkeypatch):
    from tools.agriculture.agronomy import planting_calendar_tool

    viz_reset()
    text = planting_calendar_tool.invoke({"crop": "tomato", "zone": 6})
    assert isinstance(text, str)
    assert "Planting" in text
    assert "Days to maturity" in text
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "calendar"
    assert specs[0]["source_tool"] == "planting_calendar_tool"
    kinds = {e["kind"] for e in specs[0]["data"]["events"]}
    assert "plant" in kinds
    assert "harvest" in kinds
    assert specs[0]["data"]["month"] == 4


def test_planting_unknown_crop_no_viz():
    from tools.agriculture.agronomy import planting_calendar_tool

    viz_reset()
    text = planting_calendar_tool.invoke({"crop": "not-a-crop", "zone": 6})
    assert "No planting-window" in text
    assert viz_take() == []


def test_activity_log_emits_calendar(monkeypatch):
    from tools.agriculture.precision_ag import get_field_activity_log_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr(
        "tools.agriculture.precision_ag._query",
        lambda *a, **k: [
            {
                "activitydate": "2026-04-20",
                "activitytype": "Planting",
                "product": "corn",
                "rate": None,
                "rateunit": None,
                "operatorname": "Sam",
                "notes": "",
            },
            {
                "activitydate": "2026-08-01",
                "activitytype": "Spray",
                "product": "fungicide",
                "rate": 1.2,
                "rateunit": "pt/ac",
                "operatorname": "",
                "notes": "",
            },
            {
                "activitydate": "2026-08-11",
                "activitytype": "Harvest",
                "product": "",
                "rate": None,
                "rateunit": None,
                "operatorname": "",
                "notes": "",
            },
        ],
    )
    viz_reset()
    text = get_field_activity_log_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert isinstance(text, str)
    assert "Planting" in text
    specs = viz_take()
    assert len(specs) == 1
    assert specs[0]["type"] == "calendar"
    kinds = [e["kind"] for e in specs[0]["data"]["events"]]
    assert "plant" in kinds
    assert "harvest" in kinds
    assert "activity" in kinds
    assert specs[0]["data"]["month"] == 8


def test_activity_log_empty_no_viz(monkeypatch):
    from tools.agriculture.precision_ag import get_field_activity_log_tool

    _patch_field(monkeypatch)
    monkeypatch.setattr("tools.agriculture.precision_ag._query", lambda *a, **k: [])
    viz_reset()
    text = get_field_activity_log_tool.invoke({"field_id": 12, "people_id": "5699"})
    assert "No activities" in text
    assert viz_take() == []

