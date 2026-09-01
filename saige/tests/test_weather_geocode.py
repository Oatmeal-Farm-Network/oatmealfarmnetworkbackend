"""Weather geocoder: ZIP / state abbreviation should uniquely resolve Fremont CA."""
from tools.weather.weather import WeatherService

_FREMONT_HITS = [
    {
        "city": "Fremont",
        "state": "California",
        "country": "US",
        "display_name": "Fremont, California, US",
        "lat": 37.5483,
        "lon": -121.9886,
    },
    {
        "city": "Fremont",
        "state": "Nebraska",
        "country": "US",
        "display_name": "Fremont, Nebraska, US",
        "lat": 41.4333,
        "lon": -96.4892,
    },
    {
        "city": "Fremont",
        "state": "Ohio",
        "country": "US",
        "display_name": "Fremont, Ohio, US",
        "lat": 41.3503,
        "lon": -83.1219,
    },
]


def _svc(monkeypatch, hits=None):
    svc = WeatherService()
    monkeypatch.setattr(svc, "_available", False)
    monkeypatch.setattr(svc, "_http_ok", True)
    monkeypatch.setattr(svc, "_fetch_zip_location", lambda zip_code: None)
    monkeypatch.setattr(svc, "_fetch_openweathermap_geocode", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_fetch_weatherapi_geocode", lambda *a, **k: [])
    monkeypatch.setattr(
        svc,
        "_fetch_open_meteo_geocode",
        lambda *a, **k: list(hits if hits is not None else _FREMONT_HITS),
    )
    return svc


def test_queries_expand_ca_and_skip_city_only():
    svc = WeatherService()
    variants = [v.lower() for v in svc._generate_location_queries("Fremont, CA 94538")]
    joined = " | ".join(variants)
    assert "california" in joined
    assert not any(v.strip() == "fremont" for v in variants)
    assert not any(v.strip() == "94538" for v in variants)


def test_zip_short_circuits_other_fremonts(monkeypatch):
    svc = WeatherService()
    monkeypatch.setattr(
        svc,
        "_fetch_zip_location",
        lambda zip_code: {
            "city": "Fremont",
            "state": "California",
            "country": "US",
            "display_name": "Fremont, California, US",
            "lat": 37.5483,
            "lon": -121.9886,
        },
    )
    result = svc.resolve_location("Fremont, CA 94538")
    assert result["status"] == "resolved"
    assert result["canonical_location"] == "Fremont, California, US"


def test_fremont_california_does_not_ask_nebraska(monkeypatch):
    svc = _svc(monkeypatch)
    result = svc.resolve_location("Fremont, California")
    assert result["status"] == "resolved"
    assert "California" in result["canonical_location"]
    assert "Nebraska" not in result["canonical_location"]


def test_fremont_ca_zip_without_zip_api_still_california(monkeypatch):
    svc = _svc(monkeypatch)
    result = svc.resolve_location("Fremont, CA 94538")
    assert result["status"] == "resolved"
    assert result["canonical_location"] == "Fremont, California, US"


def test_duplicate_california_coords_collapse(monkeypatch):
    dupes = [
        {**_FREMONT_HITS[0], "lat": 37.5483, "lon": -121.9886},
        {**_FREMONT_HITS[0], "lat": 37.5429, "lon": -121.9728},
        _FREMONT_HITS[1],
    ]
    svc = _svc(monkeypatch, hits=dupes)
    result = svc.resolve_location("Fremont, California, US")
    assert result["status"] == "resolved"
    assert result["canonical_location"] == "Fremont, California, US"
