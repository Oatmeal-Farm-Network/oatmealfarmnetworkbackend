"""US weather geocoder: any city/state/ZIP, not one hardcoded place."""
from tools.weather.weather import WeatherService, _US_STATE_ABBREV


def test_state_abbreviations_cover_all_us_states_and_dc():
    assert len(_US_STATE_ABBREV) == 51
    assert _US_STATE_ABBREV["ca"] == "california"
    assert _US_STATE_ABBREV["me"] == "maine"
    assert _US_STATE_ABBREV["or"] == "oregon"
    assert _US_STATE_ABBREV["dc"] == "district of columbia"


def _same_city_hits(city, wanted_state, other_states):
    wanted = {
        "city": city,
        "state": wanted_state,
        "country": "US",
        "display_name": f"{city}, {wanted_state}, US",
        "lat": 1.0,
        "lon": -1.0,
    }
    others = [
        {
            "city": city,
            "state": other,
            "country": "US",
            "display_name": f"{city}, {other}, US",
            "lat": float(i + 2),
            "lon": float(-(i + 2)),
        }
        for i, other in enumerate(other_states)
    ]
    return [wanted, *others]


def _svc(monkeypatch, hits):
    svc = WeatherService()
    monkeypatch.setattr(svc, "_available", False)
    monkeypatch.setattr(svc, "_http_ok", True)
    monkeypatch.setattr(svc, "_fetch_zip_location", lambda zip_code: None)
    monkeypatch.setattr(svc, "_fetch_openweathermap_geocode", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_fetch_weatherapi_geocode", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_fetch_open_meteo_geocode", lambda *a, **k: list(hits))
    return svc


def test_extracts_city_state_zip_from_many_us_places():
    svc = WeatherService()
    assert svc.extract_us_place_query("Fremont, CA 94538") == "Fremont, CA 94538"
    assert svc.extract_us_place_query("Portland, ME") == "Portland, ME"
    assert svc.extract_us_place_query("Springfield, IL") == "Springfield, IL"
    assert svc.extract_us_place_query("Des Moines, Iowa") == "Des Moines, Iowa"
    assert svc.extract_us_place_query("Miami, FL") == "Miami, FL"
    assert svc.extract_us_place_query("Austin TX") == "Austin, TX"
    assert svc.extract_us_place_query("what's todays weather report in fremont CA").startswith("Fremont, CA")
    assert svc.extract_us_place_query("10001") == "10001"


def test_queries_keep_state_and_never_city_only():
    svc = WeatherService()
    for raw, needle in (
        ("Portland, ME", "maine"),
        ("Springfield, IL", "illinois"),
        ("Fremont, CA 94538", "california"),
        ("Des Moines, Iowa", "iowa"),
    ):
        variants = [v.lower() for v in svc._generate_location_queries(raw)]
        joined = " | ".join(variants)
        assert needle in joined
        city = raw.split(",")[0].strip().lower()
        assert not any(v.strip() == city for v in variants)


def test_zip_resolves_whatever_city_the_zip_api_returns(monkeypatch):
    svc = WeatherService()
    monkeypatch.setattr(
        svc,
        "_fetch_zip_location",
        lambda zip_code: {
            "city": "New York",
            "state": "New York",
            "country": "US",
            "display_name": "New York, New York, US",
            "lat": 40.75,
            "lon": -73.99,
        },
    )
    result = svc.resolve_location("10001")
    assert result["status"] == "resolved"
    assert result["canonical_location"] == "New York, New York, US"


def test_this_turn_us_place_overrides_saved_farm_location(monkeypatch):
    from graph.nodes import weather_advisory_node

    seen = {}

    def fake_resolve(loc, orig="", limit=5):
        seen["loc"] = loc
        return {
            "status": "resolved",
            "canonical_location": loc,
            "lat": 25.76,
            "lon": -80.19,
            "confidence": 1.0,
        }

    monkeypatch.setattr("graph.nodes.weather_service.resolve_location", fake_resolve)
    monkeypatch.setattr(
        "graph.nodes.weather_service.get_weather",
        lambda *a, **k: {"location": "Miami, Florida, US", "current": {"temperature": 84, "condition": "Sunny"}},
    )
    monkeypatch.setattr("graph.nodes.weather_service.format_for_llm", lambda data: "Sunny 84F")
    monkeypatch.setattr("graph.nodes.weather_service.get_forecast", lambda *a, **k: None)
    out = weather_advisory_node({
        "location": "Jackson County, Oregon",
        "current_issues": ["what's todays weather report in fremont CA"],
        "assessment_summary": "",
        "history": ["User: Miami, FL"],
        "user_message": "Miami, FL",
    })
    assert "Miami" in seen.get("loc", "")
    assert "Oregon" not in seen.get("loc", "")
    assert "Miami" in out["diagnosis"]


def test_state_disambiguates_duplicate_us_city_names(monkeypatch):
    cases = [
        ("Portland, ME", "Maine", ["Oregon"]),
        ("Portland, OR", "Oregon", ["Maine"]),
        ("Springfield, IL", "Illinois", ["Missouri", "Massachusetts"]),
        ("Kansas City, KS", "Kansas", ["Missouri"]),
        ("Fremont, California", "California", ["Nebraska", "Ohio"]),
    ]
    for query, wanted, others in cases:
        city = query.split(",")[0].strip()
        svc = _svc(monkeypatch, _same_city_hits(city, wanted, others))
        result = svc.resolve_location(query)
        assert result["status"] == "resolved", query
        assert wanted in result["canonical_location"], query
        for other in others:
            assert other not in result["canonical_location"], query


def test_open_meteo_current_fills_humidity_wind_pressure():
    from tools.weather.weather import _is_stub_current, _open_meteo_current

    parsed = _open_meteo_current({
        "current": {
            "temperature_2m": 15.4,
            "apparent_temperature": 14.8,
            "relative_humidity_2m": 72,
            "weather_code": 2,
            "wind_speed_10m": 11.2,
            "surface_pressure": 1013.2,
            "cloud_cover": 40,
        }
    })
    assert parsed["temperature"] == 15
    assert parsed["condition"] == "Partly cloudy"
    assert parsed["humidity"] == 72
    assert parsed["wind_speed"] == 11.2
    assert parsed["pressure"] == 1013
    assert not _is_stub_current(parsed)


def test_format_for_llm_omits_stub_condition_and_missing_details():
    from tools.weather.weather import WeatherService

    text = WeatherService().format_for_llm({
        "temperature": 15,
        "feels_like": 15,
        "condition": "Current conditions",
        "humidity": None,
        "wind_speed": None,
        "pressure": None,
    })
    assert "Temperature: 15C" in text
    assert "Condition:" not in text
    assert "Humidity:" not in text
    assert "Wind Speed:" not in text
    assert "Pressure:" not in text
