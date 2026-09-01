"""US weather geocoder: any city/state/ZIP, not one hardcoded place."""
from tools.weather.us_states import USPS_STATES, ABBREV_TO_NAME
from tools.weather.weather import WeatherService

# Official USPS set from the 50 states + DC chart.
_EXPECTED_USPS = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DC": "District of Columbia", "DE": "Delaware", "FL": "Florida",
    "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def test_usps_table_matches_official_50_states_and_dc():
    assert USPS_STATES == _EXPECTED_USPS
    assert len(USPS_STATES) == 51
    assert ABBREV_TO_NAME["ca"] == "california"
    assert ABBREV_TO_NAME["me"] == "maine"
    assert ABBREV_TO_NAME["or"] == "oregon"
    assert ABBREV_TO_NAME["dc"] == "district of columbia"


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
