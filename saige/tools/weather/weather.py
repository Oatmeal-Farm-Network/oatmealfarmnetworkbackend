# --- tools/weather/weather.py ---
import os
import re
import time
from difflib import SequenceMatcher
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool
from config import WEATHER_AVAILABLE
from visualizations.pending import viz_emit

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    requests = None  # type: ignore
    _REQUESTS_OK = False

# Lowercase USPS abbreviations → full state/region names. Used so "CA" matches
# OpenWeather/Open-Meteo "California" and so we do not geocode city-only variants.
_US_STATE_ABBREV = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "dc": "district of columbia", "fl": "florida", "ga": "georgia", "hi": "hawaii",
    "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa",
    "ks": "kansas", "ky": "kentucky", "la": "louisiana", "me": "maine",
    "md": "maryland", "ma": "massachusetts", "mi": "michigan", "mn": "minnesota",
    "ms": "mississippi", "mo": "missouri", "mt": "montana", "ne": "nebraska",
    "nv": "nevada", "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico",
    "ny": "new york", "nc": "north carolina", "nd": "north dakota", "oh": "ohio",
    "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania", "ri": "rhode island",
    "sc": "south carolina", "sd": "south dakota", "tn": "tennessee", "tx": "texas",
    "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington",
    "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming",
}
_US_STATE_NAMES = set(_US_STATE_ABBREV.values())
_COUNTRY_TOKENS = {"us", "usa", "united states", "unitedstates"}
_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
_PLACE_NOISE = frozenset({
    "weather", "forecast", "temperature", "rain", "climate", "report", "today",
    "todays", "what's", "whats", "the", "a", "an", "my", "our", "your", "this",
    "coming", "days", "day", "week", "weeks", "month", "months", "please",
    "check", "can", "you", "in", "at", "near", "for", "about", "current",
})
_US_STATE_PATTERN = "(?:%s|%s)" % (
    "|".join(re.escape(name) for name in sorted(_US_STATE_NAMES, key=len, reverse=True)),
    "|".join(re.escape(abbr) for abbr in sorted(_US_STATE_ABBREV, key=len, reverse=True)),
)


class WeatherService:
    """Weather service for fetching current and forecast data from weather APIs."""

    def __init__(self):
        self._api_key = os.getenv("WEATHER_API_KEY", "").strip()
        self._provider = os.getenv("WEATHER_API_PROVIDER", "openweathermap").strip().lower()
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        # Primary providers need a key; Open-Meteo fallback works without one.
        self._available = bool(WEATHER_AVAILABLE and _REQUESTS_OK and self._api_key)
        self._http_ok = bool(_REQUESTS_OK)

    def _is_cache_valid(self, location: str) -> bool:
        """Check if cached data is still valid."""
        if location not in self._cache:
            return False
        data, timestamp = self._cache[location]
        return (time.time() - timestamp) < self._cache_ttl

    def _get_from_cache(self, location: str) -> Optional[Dict[str, Any]]:
        """Get weather data from cache if valid."""
        if self._is_cache_valid(location):
            return self._cache[location][0]
        return None

    def _save_to_cache(self, location: str, data: Dict[str, Any]):
        """Save weather data to cache."""
        self._cache[location] = (data, time.time())

    @staticmethod
    def _normalize_location_text(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s,\-]", " ", (text or "").lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
        return cleaned

    @staticmethod
    def _collapse_location_text(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (text or "").lower())

    @staticmethod
    def _build_display_name(city: str, state: str, country: str) -> str:
        parts = [part for part in [city, state, country] if part]
        return ", ".join(parts)

    @staticmethod
    def _extract_us_zip(text: str) -> Optional[str]:
        match = _ZIP_RE.search(text or "")
        return match.group(1) if match else None

    @classmethod
    def extract_us_place_query(cls, text: str) -> Optional[str]:
        """Pull a US city/state/ZIP from free text. Works for any US place, not one city."""
        raw = (text or "").strip()
        if not raw:
            return None
        zip_code = cls._extract_us_zip(raw)
        matches = []
        pattern = re.compile(
            rf"(?i)\b(?P<city>[A-Za-z][A-Za-z.'\-]+(?:\s+[A-Za-z][A-Za-z.'\-]+){{0,3}})"
            rf"\s*,?\s+(?P<state>{_US_STATE_PATTERN})\b"
            rf"(?:\s+(?P<zip>\d{{5}}))?"
        )
        for match in pattern.finditer(raw):
            city_parts = [
                part for part in re.split(r"\s+", (match.group("city") or "").strip())
                if part and part.lower() not in _PLACE_NOISE
            ]
            if not city_parts:
                continue
            city = " ".join(city_parts)
            if city.lower() in _US_STATE_NAMES or city.lower() in _US_STATE_ABBREV:
                continue
            matches.append((city, match.group("state"), match.group("zip") or zip_code))
        chosen = None
        for item in matches:
            if item[2]:
                chosen = item
                break
        if not chosen and matches:
            chosen = matches[-1]
        if chosen:
            city, state, zipp = chosen
            state_fmt = state.upper() if len(state) == 2 else state.title()
            city_fmt = " ".join(
                w.capitalize() if w.lower() != "of" else w.lower() for w in city.split()
            )
            out = f"{city_fmt}, {state_fmt}"
            if zipp:
                out = f"{out} {zipp}"
            return out
        if zip_code:
            return zip_code
        return None

    @staticmethod
    def _expand_us_tokens(tokens: List[str]) -> List[str]:
        expanded: List[str] = []
        for tok in tokens:
            low = tok.lower()
            if low in _US_STATE_ABBREV:
                expanded.append(_US_STATE_ABBREV[low])
            elif low in ("usa", "unitedstates"):
                expanded.append("us")
            else:
                expanded.append(low)
        return expanded

    @classmethod
    def _canonical_location_text(cls, text: str) -> str:
        tokens = [tok for tok in re.split(r"[\s,]+", cls._normalize_location_text(text)) if tok]
        return " ".join(cls._expand_us_tokens(tokens))

    @classmethod
    def _canonical_state(cls, state: str) -> str:
        low = (state or "").strip().lower()
        return _US_STATE_ABBREV.get(low, low)

    @staticmethod
    def _canonical_country(country: str) -> str:
        low = (country or "").strip().lower()
        if low in _COUNTRY_TOKENS or low == "united states of america":
            return "us"
        return low

    @classmethod
    def _state_from_query(cls, text: str) -> Optional[str]:
        tokens = cls._expand_us_tokens(
            [tok for tok in re.split(r"[\s,]+", cls._normalize_location_text(text)) if tok]
        )
        for tok in tokens:
            if tok in _US_STATE_NAMES:
                return tok
        return None

    @classmethod
    def _states_match(cls, candidate_state: str, wanted_state: str) -> bool:
        return cls._canonical_state(candidate_state) == cls._canonical_state(wanted_state)

    @classmethod
    def _place_key(cls, candidate: Dict[str, Any]) -> str:
        city = cls._collapse_location_text(candidate.get("city") or "")
        state = cls._collapse_location_text(cls._canonical_state(candidate.get("state") or ""))
        country = cls._collapse_location_text(cls._canonical_country(candidate.get("country") or ""))
        return f"{city}|{state}|{country}"

    def _generate_location_queries(self, location_query: str, max_queries: int = 5) -> List[str]:
        """Name variants for geocoders. Never drop a stated state/ZIP down to city-only."""
        zip_code = self._extract_us_zip(location_query)
        raw_tokens = [
            tok for tok in re.split(r"[\s,]+", self._normalize_location_text(location_query)) if tok
        ]
        tokens = self._expand_us_tokens(raw_tokens)
        name_tokens = [
            tok for tok in tokens
            if not (tok.isdigit() and len(tok) == 5) and tok not in _COUNTRY_TOKENS
        ]
        state_idx = None
        for i, tok in enumerate(name_tokens):
            if tok in _US_STATE_NAMES:
                state_idx = i
        if state_idx is not None and state_idx > 0:
            city_tokens = name_tokens[:state_idx]
            state_name = name_tokens[state_idx]
        else:
            city_tokens = [tok for tok in name_tokens if tok not in _US_STATE_NAMES]
            state_name = next((tok for tok in name_tokens if tok in _US_STATE_NAMES), None)

        queries: List[str] = []

        def _push(q: str):
            q = q.strip(" ,")
            if not q or q in queries:
                return
            parts = [p for p in re.split(r"[\s,]+", q) if p]
            if len(parts) == 1 and len(parts[0]) < 4:
                return
            queries.append(q)

        if city_tokens and state_name:
            city = " ".join(city_tokens)
            _push(f"{city}, {state_name}")
            _push(f"{city}, {state_name}, US")
            _push(f"{city} {state_name}")
        elif name_tokens:
            _push(" ".join(name_tokens))
            if len(name_tokens) >= 2:
                _push(f"{name_tokens[0]}, {' '.join(name_tokens[1:])}")
            # City-only / suffix variants only when the user did not name a state or ZIP.
            if not state_name and not zip_code and len(name_tokens) > 1:
                for end in range(len(name_tokens) - 1, 0, -1):
                    _push(" ".join(name_tokens[:end]))
                for start in range(1, len(name_tokens)):
                    chunk = " ".join(name_tokens[start:])
                    if len(chunk) >= 4:
                        _push(chunk)

        return queries[:max_queries] or [location_query.strip()]

    def _fetch_zip_location(self, zip_code: str) -> Optional[Dict[str, Any]]:
        """Resolve a US ZIP via Zippopotam (no API key)."""
        if not _REQUESTS_OK or not zip_code:
            return None
        try:
            response = requests.get(f"https://api.zippopotam.us/us/{zip_code}", timeout=5)
            if response.status_code != 200:
                return None
            data = response.json() or {}
            places = data.get("places") or []
            if not places:
                return None
            place = places[0]
            city = place.get("place name") or ""
            state = place.get("state") or ""
            country = data.get("country abbreviation") or "US"
            return {
                "city": city,
                "state": state,
                "country": country,
                "display_name": self._build_display_name(city, state, country),
                "lat": float(place.get("latitude")),
                "lon": float(place.get("longitude")),
            }
        except Exception as e:
            print(f"[Weather] ZIP geocode error: {e}")
            return None

    def _fetch_openweathermap_geocode(self, location_query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self._api_key or not _REQUESTS_OK:
            return []
        try:
            geo_url = "http://api.openweathermap.org/geo/1.0/direct"
            geo_params = {"q": location_query, "limit": limit, "appid": self._api_key}
            geo_response = requests.get(geo_url, params=geo_params, timeout=5)
            if geo_response.status_code != 200:
                print(f"[Weather] Geo API error: {geo_response.status_code}")
                return []

            entries = geo_response.json() or []
            results: List[Dict[str, Any]] = []
            for entry in entries:
                city = entry.get("name", "")
                state = entry.get("state", "")
                country = entry.get("country", "")
                results.append(
                    {
                        "city": city,
                        "state": state,
                        "country": country,
                        "display_name": self._build_display_name(city, state, country),
                        "lat": entry.get("lat"),
                        "lon": entry.get("lon"),
                    }
                )
            return results
        except Exception as e:
            print(f"[Weather] OpenWeatherMap geocode error: {e}")
            return []

    def _fetch_open_meteo_geocode(self, location_query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Key-free geocoding via Open-Meteo."""
        if not _REQUESTS_OK:
            return []
        try:
            url = "https://geocoding-api.open-meteo.com/v1/search"
            params = {"name": location_query, "count": limit, "language": "en", "format": "json"}
            if WeatherService._state_from_query(location_query) or WeatherService._extract_us_zip(location_query):
                params["countryCode"] = "US"
            response = requests.get(url, params=params, timeout=8)
            if response.status_code != 200:
                print(f"[Weather] Open-Meteo geocode error: {response.status_code}")
                return []
            results_raw = (response.json() or {}).get("results") or []
            results: List[Dict[str, Any]] = []
            for entry in results_raw:
                city = entry.get("name", "")
                state = entry.get("admin1", "") or ""
                country = entry.get("country_code", "") or entry.get("country", "") or ""
                results.append(
                    {
                        "city": city,
                        "state": state,
                        "country": country,
                        "display_name": self._build_display_name(city, state, country),
                        "lat": entry.get("latitude"),
                        "lon": entry.get("longitude"),
                    }
                )
            return results
        except Exception as e:
            print(f"[Weather] Open-Meteo geocode error: {e}")
            return []

    def _fetch_weatherapi_geocode(self, location_query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self._api_key:
            return []
        try:
            url = "https://api.weatherapi.com/v1/search.json"
            params = {"key": self._api_key, "q": location_query}
            response = requests.get(url, params=params, timeout=5)
            if response.status_code != 200:
                print(f"[Weather] WeatherAPI search error: {response.status_code}")
                return []

            entries = (response.json() or [])[:limit]
            results: List[Dict[str, Any]] = []
            for entry in entries:
                city = entry.get("name", "")
                state = entry.get("region", "")
                country = entry.get("country", "")
                results.append(
                    {
                        "city": city,
                        "state": state,
                        "country": country,
                        "display_name": self._build_display_name(city, state, country),
                        "lat": entry.get("lat"),
                        "lon": entry.get("lon"),
                    }
                )
            return results
        except Exception as e:
            print(f"[Weather] WeatherAPI search error: {e}")
            return []

    def _score_location_candidate(
        self,
        candidate_query: str,
        original_query: str,
        result: Dict[str, Any],
        variant_rank: int,
    ) -> float:
        candidate_norm = self._canonical_location_text(candidate_query)
        original_norm = self._canonical_location_text(original_query)
        candidate_compact = self._collapse_location_text(candidate_norm)
        original_compact = self._collapse_location_text(original_norm)

        city = self._collapse_location_text(result.get("city", ""))
        state = self._collapse_location_text(result.get("state", ""))
        country = self._collapse_location_text(result.get("country", ""))
        display = self._normalize_location_text(result.get("display_name", ""))

        score = 0.0

        if city and candidate_compact:
            if city in candidate_compact or candidate_compact in city:
                coverage = min(len(city), len(candidate_compact)) / max(len(city), len(candidate_compact))
                score += 0.45 + (0.25 * coverage)
            else:
                similarity = SequenceMatcher(None, city, candidate_compact).ratio()
                if similarity >= 0.72:
                    score += 0.40 * similarity

        if state and state in candidate_compact:
            score += 0.10
        if country and country in candidate_compact:
            score += 0.08

        if city and city in original_compact:
            score += 0.16
        if state and state in original_compact:
            score += 0.22
        if country and country in original_compact:
            score += 0.04

        # Strong boost when query includes the candidate's state/region name
        state_raw = (result.get("state") or "").strip().lower()
        if state_raw and state_raw in original_norm:
            score += 0.28

        candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate_norm))
        display_tokens = set(re.findall(r"[a-z0-9]+", display))
        if city:
            display_tokens.add(city)

        if candidate_tokens:
            overlap = len(candidate_tokens & display_tokens) / len(candidate_tokens)
            score += 0.18 * overlap
            score -= 0.12 * (1.0 - overlap)

        score += max(0.0, 0.04 - (0.01 * variant_rank))
        # Allow scores > 1 so state/country matches can outrank same-name cities
        return max(0.0, score)

    def resolve_location(self, location_query: str, original_query: str = "", limit: int = 5) -> Dict[str, Any]:
        """
        Resolve location text to a canonical, geocoded location.
        Returns one of: resolved, ambiguous, not_found, unavailable.
        """
        if not self._available and not self._http_ok:
            return {"status": "unavailable"}

        normalized_query = (location_query or "").strip()
        if not normalized_query or normalized_query == "Unknown":
            return {"status": "not_found", "query": location_query}

        zip_code = self._extract_us_zip(normalized_query)
        if zip_code:
            zipped = self._fetch_zip_location(zip_code)
            if zipped:
                return {
                    "status": "resolved",
                    "query": location_query,
                    "canonical_location": zipped["display_name"],
                    "confidence": 0.99,
                    "lat": zipped.get("lat"),
                    "lon": zipped.get("lon"),
                    "candidates": [zipped],
                }

        query_variants = self._generate_location_queries(normalized_query)
        scored_candidates: List[Dict[str, Any]] = []

        for variant_rank, query_variant in enumerate(query_variants):
            raw_candidates: List[Dict[str, Any]] = []
            if self._available and self._provider == "weatherapi":
                raw_candidates = self._fetch_weatherapi_geocode(query_variant, limit=limit)
            elif self._available:
                raw_candidates = self._fetch_openweathermap_geocode(query_variant, limit=limit)
            if not raw_candidates and self._http_ok:
                raw_candidates = self._fetch_open_meteo_geocode(query_variant, limit=limit)

            for candidate in raw_candidates:
                score = self._score_location_candidate(
                    candidate_query=query_variant,
                    original_query=original_query or normalized_query,
                    result=candidate,
                    variant_rank=variant_rank,
                )
                scored_candidates.append(
                    {
                        **candidate,
                        "confidence": round(score, 3),
                        "matched_query": query_variant,
                    }
                )

        if not scored_candidates:
            return {"status": "not_found", "query": location_query}

        deduped: Dict[str, Dict[str, Any]] = {}
        for candidate in scored_candidates:
            key = self._place_key(candidate)
            if key == "||":
                key = f"{round(candidate.get('lat') or 0, 4)}:{round(candidate.get('lon') or 0, 4)}"
            existing = deduped.get(key)
            if not existing or candidate["confidence"] > existing["confidence"]:
                deduped[key] = candidate

        ranked = sorted(deduped.values(), key=lambda x: x["confidence"], reverse=True)
        wanted_state = self._state_from_query(original_query or normalized_query)
        if wanted_state:
            matching = [c for c in ranked if self._states_match(c.get("state") or "", wanted_state)]
            if matching:
                ranked = matching

        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None

        # Prefer unique state/region match from the original query text
        orig_norm = self._canonical_location_text(original_query or normalized_query)
        state_hits = []
        for c in ranked:
            st = self._canonical_state(c.get("state") or "")
            if st and st in orig_norm:
                state_hits.append(c)
        if len(state_hits) == 1:
            best = state_hits[0]
            return {
                "status": "resolved",
                "query": location_query,
                "canonical_location": best["display_name"],
                "confidence": best["confidence"],
                "lat": best.get("lat"),
                "lon": best.get("lon"),
                "candidates": ranked[:3],
            }

        confidence_gap = best["confidence"] - (second["confidence"] if second else 0.0)
        is_ambiguous = second is not None and (best["confidence"] < 0.78 or confidence_gap < 0.10)

        if best["confidence"] < 0.55:
            return {
                "status": "not_found",
                "query": location_query,
                "candidates": ranked[:3],
            }

        if is_ambiguous:
            return {
                "status": "ambiguous",
                "query": location_query,
                "candidates": ranked[:3],
            }

        return {
            "status": "resolved",
            "query": location_query,
            "canonical_location": best["display_name"],
            "confidence": best["confidence"],
            "lat": best.get("lat"),
            "lon": best.get("lon"),
            "candidates": ranked[:3],
        }

    def _fetch_openweathermap(self, location: str) -> Optional[Dict[str, Any]]:
        """Fetch weather from OpenWeatherMap API."""
        if not self._api_key:
            return None
        try:
            geo_url = "http://api.openweathermap.org/geo/1.0/direct"
            geo_params = {"q": location, "limit": 1, "appid": self._api_key}
            geo_response = requests.get(geo_url, params=geo_params, timeout=5)

            if geo_response.status_code != 200:
                print(f"[Weather] Geo API error: {geo_response.status_code}")
                return None

            geo_data = geo_response.json()
            if not geo_data:
                print(f"[Weather] Location not found: {location}")
                return None

            lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]

            weather_url = "https://api.openweathermap.org/data/2.5/weather"
            weather_params = {
                "lat": lat, "lon": lon,
                "appid": self._api_key, "units": "metric"
            }
            weather_response = requests.get(weather_url, params=weather_params, timeout=5)

            if weather_response.status_code != 200:
                print(f"[Weather] Weather API error: {weather_response.status_code}")
                return None

            data = weather_response.json()

            return {
                "location": f"{geo_data[0].get('name', location)}, {geo_data[0].get('country', '')}",
                "temperature": round(data["main"]["temp"]),
                "feels_like": round(data["main"]["feels_like"]),
                "condition": data["weather"][0]["description"].title(),
                "humidity": data["main"]["humidity"],
                "wind_speed": round(data["wind"].get("speed", 0) * 3.6, 1),
                "pressure": data["main"]["pressure"],
                "clouds": data["clouds"]["all"],
                "visibility": data.get("visibility", 0) / 1000 if data.get("visibility") else None,
            }
        except Exception as e:
            print(f"[Weather] OpenWeatherMap error: {e}")
            return None

    def _fetch_weatherapi(self, location: str) -> Optional[Dict[str, Any]]:
        """Fetch weather from WeatherAPI.com."""
        if not self._api_key:
            return None
        try:
            url = "https://api.weatherapi.com/v1/current.json"
            params = {"key": self._api_key, "q": location, "aqi": "no"}
            response = requests.get(url, params=params, timeout=5)

            if response.status_code != 200:
                print(f"[Weather] WeatherAPI error: {response.status_code}")
                return None

            data = response.json()

            return {
                "location": f"{data['location']['name']}, {data['location']['country']}",
                "temperature": round(data["current"]["temp_c"]),
                "feels_like": round(data["current"]["feelslike_c"]),
                "condition": data["current"]["condition"]["text"],
                "humidity": data["current"]["humidity"],
                "wind_speed": round(data["current"]["wind_kph"], 1),
                "pressure": data["current"]["pressure_mb"],
                "clouds": data["current"]["cloud"],
                "visibility": round(data["current"]["vis_km"], 1) if data["current"].get("vis_km") else None,
            }
        except Exception as e:
            print(f"[Weather] WeatherAPI error: {e}")
            return None

    def _fetch_weatherapi_forecast(self, location: str, days: int = 5) -> Optional[Dict[str, Any]]:
        """Fetch weather forecast from WeatherAPI.com."""
        if not self._api_key:
            return None
        try:
            days = min(days, 10)
            url = "https://api.weatherapi.com/v1/forecast.json"
            params = {"key": self._api_key, "q": location, "days": days, "aqi": "no"}
            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                print(f"[Weather] WeatherAPI forecast error: {response.status_code}")
                return None

            data = response.json()

            forecast_days = []
            for day in data.get("forecast", {}).get("forecastday", []):
                forecast_days.append({
                    "date": day["date"],
                    "max_temp": round(day["day"]["maxtemp_c"]),
                    "min_temp": round(day["day"]["mintemp_c"]),
                    "avg_temp": round(day["day"]["avgtemp_c"]),
                    "condition": day["day"]["condition"]["text"],
                    "rain_chance": day["day"].get("daily_chance_of_rain", 0),
                    "humidity": day["day"].get("avghumidity", 0),
                    "max_wind": round(day["day"].get("maxwind_kph", 0), 1),
                })

            return {
                "location": f"{data['location']['name']}, {data['location']['country']}",
                "current": {
                    "temperature": round(data["current"]["temp_c"]),
                    "condition": data["current"]["condition"]["text"],
                },
                "forecast": forecast_days,
                "forecast_days": len(forecast_days),
            }
        except Exception as e:
            print(f"[Weather] WeatherAPI forecast error: {e}")
            return None

    def get_forecast(
        self,
        location: str,
        days: int = 5,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch weather forecast for location (optionally using resolved coords)."""
        if not location or location == "Unknown":
            if lat is None or lon is None:
                return None

        days = max(1, min(int(days or 5), 7))
        print(f"[Weather] Fetching {days}-day forecast for {location} (lat={lat}, lon={lon})...")

        data = None
        if self._available and self._provider == "weatherapi":
            q = f"{lat},{lon}" if lat is not None and lon is not None else location
            data = self._fetch_weatherapi_forecast(q, days)
        elif self._available and self._provider != "weatherapi" and lat is not None and lon is not None:
            data = self._fetch_openweathermap_forecast(lat, lon, days, location)
        elif self._available and self._provider != "weatherapi":
            # Resolve once then forecast by coords
            resolved = self.resolve_location(location)
            if resolved.get("status") == "resolved" and resolved.get("lat") is not None:
                data = self._fetch_openweathermap_forecast(
                    float(resolved["lat"]), float(resolved["lon"]), days, resolved.get("canonical_location") or location
                )

        if not data and lat is not None and lon is not None:
            data = self._fetch_open_meteo_forecast(float(lat), float(lon), days, location)
        if not data:
            resolved = self.resolve_location(location) if location and location != "Unknown" else None
            if resolved and resolved.get("status") == "resolved" and resolved.get("lat") is not None:
                data = self._fetch_open_meteo_forecast(
                    float(resolved["lat"]),
                    float(resolved["lon"]),
                    days,
                    resolved.get("canonical_location") or location,
                )

        if data:
            print(f"[Weather] Forecast data retrieved ({data.get('forecast_days')} days)")
        return data

    def _fetch_openweathermap_forecast(
        self, lat: float, lon: float, days: int, location_label: str
    ) -> Optional[Dict[str, Any]]:
        """OWM free 5-day / 3-hour forecast, aggregated to daily min/max."""
        if not self._api_key:
            return None
        try:
            url = "https://api.openweathermap.org/data/2.5/forecast"
            params = {"lat": lat, "lon": lon, "appid": self._api_key, "units": "metric"}
            response = requests.get(url, params=params, timeout=8)
            if response.status_code != 200:
                print(f"[Weather] OWM forecast error: {response.status_code}")
                return None
            payload = response.json() or {}
            entries = payload.get("list") or []
            if not entries:
                return None
            by_day: Dict[str, Dict[str, Any]] = {}
            for entry in entries:
                dt_txt = str(entry.get("dt_txt") or "")
                day = dt_txt.split(" ")[0] if dt_txt else ""
                if not day:
                    continue
                main = entry.get("main") or {}
                weather = (entry.get("weather") or [{}])[0]
                wind = entry.get("wind") or {}
                pop = float(entry.get("pop") or 0) * 100
                slot = by_day.setdefault(
                    day,
                    {
                        "date": day,
                        "min_temp": main.get("temp_min"),
                        "max_temp": main.get("temp_max"),
                        "condition": weather.get("description", "").title(),
                        "rain_chance": pop,
                        "max_wind": round(float(wind.get("speed") or 0) * 3.6, 1),
                    },
                )
                tmin = main.get("temp_min")
                tmax = main.get("temp_max")
                if tmin is not None:
                    slot["min_temp"] = min(slot["min_temp"], tmin) if slot["min_temp"] is not None else tmin
                if tmax is not None:
                    slot["max_temp"] = max(slot["max_temp"], tmax) if slot["max_temp"] is not None else tmax
                slot["rain_chance"] = max(slot.get("rain_chance") or 0, pop)
            forecast_days = []
            for day in sorted(by_day.keys())[:days]:
                slot = by_day[day]
                forecast_days.append(
                    {
                        "date": day,
                        "min_temp": round(slot["min_temp"]) if slot.get("min_temp") is not None else None,
                        "max_temp": round(slot["max_temp"]) if slot.get("max_temp") is not None else None,
                        "condition": slot.get("condition") or "",
                        "rain_chance": int(slot.get("rain_chance") or 0),
                        "max_wind": slot.get("max_wind") or 0,
                    }
                )
            city = (payload.get("city") or {}).get("name") or location_label
            country = (payload.get("city") or {}).get("country") or ""
            label = f"{city}, {country}".strip(", ")
            current = entries[0]
            return {
                "location": label or location_label,
                "current": {
                    "temperature": round((current.get("main") or {}).get("temp") or 0),
                    "condition": ((current.get("weather") or [{}])[0].get("description") or "").title(),
                },
                "forecast": forecast_days,
                "forecast_days": len(forecast_days),
            }
        except Exception as e:
            print(f"[Weather] OWM forecast error: {e}")
            return None

    def _fetch_open_meteo_forecast(
        self, lat: float, lon: float, days: int, location_label: str
    ) -> Optional[Dict[str, Any]]:
        """Key-free Open-Meteo daily forecast fallback."""
        if not _REQUESTS_OK:
            return None
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                "current_weather": "true",
                "forecast_days": days,
                "timezone": "auto",
            }
            response = requests.get(url, params=params, timeout=8)
            if response.status_code != 200:
                print(f"[Weather] Open-Meteo error: {response.status_code}")
                return None
            data = response.json() or {}
            daily = data.get("daily") or {}
            dates = daily.get("time") or []
            tmax = daily.get("temperature_2m_max") or []
            tmin = daily.get("temperature_2m_min") or []
            rain = daily.get("precipitation_probability_max") or []
            codes = daily.get("weathercode") or []
            code_map = {
                0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Fog", 48: "Depositing rime fog",
                51: "Light drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
                71: "Light snow", 73: "Snow", 75: "Heavy snow",
                80: "Rain showers", 95: "Thunderstorm",
            }
            forecast_days = []
            for i, day in enumerate(dates[:days]):
                forecast_days.append(
                    {
                        "date": day,
                        "min_temp": round(tmin[i]) if i < len(tmin) and tmin[i] is not None else None,
                        "max_temp": round(tmax[i]) if i < len(tmax) and tmax[i] is not None else None,
                        "condition": code_map.get(int(codes[i]) if i < len(codes) and codes[i] is not None else -1, "Varying conditions"),
                        "rain_chance": int(rain[i]) if i < len(rain) and rain[i] is not None else 0,
                        "max_wind": 0,
                    }
                )
            current = data.get("current_weather") or {}
            return {
                "location": location_label,
                "current": {
                    "temperature": round(current.get("temperature") or 0),
                    "condition": code_map.get(int(current.get("weathercode") or -1), "Current conditions"),
                },
                "forecast": forecast_days,
                "forecast_days": len(forecast_days),
            }
        except Exception as e:
            print(f"[Weather] Open-Meteo forecast error: {e}")
            return None

    def format_forecast_for_llm(self, forecast_data: Optional[Dict[str, Any]]) -> str:
        """Format forecast data as context string for LLM."""
        if not forecast_data or not forecast_data.get("forecast"):
            return ""

        parts = [f"Weather forecast for {forecast_data['location']}:\n"]

        if forecast_data.get("current"):
            parts.append(f"Current: {forecast_data['current']['temperature']}C, {forecast_data['current']['condition']}\n")

        parts.append("Forecast:")
        for day in forecast_data["forecast"]:
            rain_str = f", {day['rain_chance']}% rain" if day.get('rain_chance', 0) > 0 else ""
            parts.append(f"  {day['date']}: {day['min_temp']}C - {day['max_temp']}C, {day['condition']}{rain_str}")

        return "\n".join(parts)

    def get_weather(
        self,
        location: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch current weather for location (optionally using resolved coords)."""
        if (not location or location == "Unknown") and (lat is None or lon is None):
            return None

        cache_key = location if location and location != "Unknown" else f"{lat},{lon}"
        cached = self._get_from_cache(cache_key)
        if cached:
            print(f"[Weather] Using cached data for {cache_key}")
            return cached

        print(f"[Weather] Fetching weather for {cache_key}...")
        data = None
        if self._available:
            if lat is not None and lon is not None and self._provider != "weatherapi":
                data = self._fetch_openweathermap_by_coords(float(lat), float(lon), location or cache_key)
            elif self._provider == "weatherapi":
                q = f"{lat},{lon}" if lat is not None and lon is not None else location
                data = self._fetch_weatherapi(q)
            else:
                data = self._fetch_openweathermap(location)

        if not data and lat is not None and lon is not None:
            forecast = self._fetch_open_meteo_forecast(float(lat), float(lon), 1, location or cache_key)
            if forecast and forecast.get("current"):
                data = {
                    "location": forecast.get("location") or location or cache_key,
                    "temperature": forecast["current"]["temperature"],
                    "feels_like": forecast["current"]["temperature"],
                    "condition": forecast["current"]["condition"],
                    "humidity": 0,
                    "wind_speed": 0,
                    "pressure": 0,
                    "clouds": 0,
                    "visibility": None,
                }

        if data:
            self._save_to_cache(cache_key, data)
            print(f"[Weather] Weather data retrieved")

        return data

    def _fetch_openweathermap_by_coords(
        self, lat: float, lon: float, location_label: str
    ) -> Optional[Dict[str, Any]]:
        if not self._api_key:
            return None
        try:
            weather_url = "https://api.openweathermap.org/data/2.5/weather"
            weather_params = {
                "lat": lat, "lon": lon,
                "appid": self._api_key, "units": "metric"
            }
            weather_response = requests.get(weather_url, params=weather_params, timeout=5)
            if weather_response.status_code != 200:
                print(f"[Weather] Weather API error: {weather_response.status_code}")
                return None
            data = weather_response.json()
            return {
                "location": location_label or f"{lat},{lon}",
                "temperature": round(data["main"]["temp"]),
                "feels_like": round(data["main"]["feels_like"]),
                "condition": data["weather"][0]["description"].title(),
                "humidity": data["main"]["humidity"],
                "wind_speed": round(data["wind"].get("speed", 0) * 3.6, 1),
                "pressure": data["main"]["pressure"],
                "clouds": data["clouds"]["all"],
                "visibility": data.get("visibility", 0) / 1000 if data.get("visibility") else None,
            }
        except Exception as e:
            print(f"[Weather] OpenWeatherMap coords error: {e}")
            return None

    def format_for_llm(self, weather_data: Optional[Dict[str, Any]]) -> str:
        """Format weather data as context string for LLM."""
        if not weather_data:
            return ""

        parts = ["Current weather conditions:\n"]
        parts.append(f"Temperature: {weather_data['temperature']}C (feels like {weather_data['feels_like']}C)")
        parts.append(f"Condition: {weather_data['condition']}")
        parts.append(f"Humidity: {weather_data['humidity']}%")
        parts.append(f"Wind Speed: {weather_data['wind_speed']} km/h")
        parts.append(f"Pressure: {weather_data['pressure']} hPa")
        if weather_data.get('visibility'):
            parts.append(f"Visibility: {weather_data['visibility']} km")

        return "\n".join(parts)


def emit_weather_visualizations(
    forecast_data: Optional[Dict[str, Any]],
    source_tool: str = "get_weather_tool",
) -> None:
    """Emit line_chart specs from forecast daily arrays. No-op if too few points.

    Keeps format_for_llm / format_forecast_for_llm as the spoken text. LineChartViz
    plots one yKey, so high temp and rain chance are two line_chart specs (not a
    new type). min_temp is included on the temp series for later dual-line chrome.
    """
    if not isinstance(forecast_data, dict):
        return
    days = forecast_data.get("forecast")
    if not isinstance(days, list):
        return

    temp_series: List[Dict[str, Any]] = []
    rain_series: List[Dict[str, Any]] = []
    for day in days:
        if not isinstance(day, dict) or not day.get("date"):
            continue
        date = str(day.get("date"))
        try:
            if day.get("max_temp") is not None:
                point: Dict[str, Any] = {
                    "date": date,
                    "max_temp": float(day.get("max_temp")),
                }
                if day.get("min_temp") is not None:
                    point["min_temp"] = float(day.get("min_temp"))
                temp_series.append(point)
        except (TypeError, ValueError):
            pass
        try:
            if day.get("rain_chance") is not None:
                rain_series.append({
                    "date": date,
                    "rain_chance": float(day.get("rain_chance")),
                })
        except (TypeError, ValueError):
            pass

    loc = str(forecast_data.get("location") or "").strip() or "forecast"

    if len(temp_series) >= 2:
        viz_emit({
            "id": "weather_high",
            "type": "line_chart",
            "title": f"Forecast high — {loc}",
            "source_tool": source_tool,
            "data": {
                "xKey": "date",
                "yKey": "max_temp",
                "unit": "°C",
                "series": temp_series[-90:],
            },
            "actions": [],
        })
    if len(rain_series) >= 2:
        viz_emit({
            "id": "weather_rain",
            "type": "line_chart",
            "title": f"Rain chance — {loc}",
            "source_tool": source_tool,
            "data": {
                "xKey": "date",
                "yKey": "rain_chance",
                "unit": "%",
                "series": rain_series[-90:],
            },
            "actions": [],
        })


weather_service = WeatherService()


@tool
def get_weather_tool(location: str) -> str:
    """Get current weather conditions for a specific location.

    Use this tool when weather information is needed to provide accurate farm advice.
    The location can be a city name, region, or any geographic location.

    Args:
        location: The location to get weather for (e.g., "Boston", "New York", "North region")

    Returns:
        A formatted string with current weather conditions including temperature,
        condition, humidity, wind speed, and pressure.
    """
    weather_data = weather_service.get_weather(location)
    if not weather_data:
        return f"Unable to fetch weather data for {location}. Please check the location name or try again later."

    try:
        forecast = weather_service.get_forecast(location, days=7)
        emit_weather_visualizations(forecast, source_tool="get_weather_tool")
    except Exception:
        pass

    return weather_service.format_for_llm(weather_data)


weather_tools = [get_weather_tool]
