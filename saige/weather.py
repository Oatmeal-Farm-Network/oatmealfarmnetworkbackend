# --- weather.py --- (Weather service + LangChain tool)
import os
import re
import time
from difflib import SequenceMatcher
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool
from config import WEATHER_AVAILABLE

if WEATHER_AVAILABLE:
    import requests


class WeatherService:
    """Weather service for fetching current and forecast data from weather APIs."""

    def __init__(self):
        self._api_key = os.getenv("WEATHER_API_KEY", "").strip()
        self._provider = os.getenv("WEATHER_API_PROVIDER", "openweathermap").strip().lower()
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._available = WEATHER_AVAILABLE and bool(self._api_key)

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

    def _generate_location_queries(self, location_query: str, max_queries: int = 5) -> List[str]:
        """
        Generate normalized location query variants without word-block lists.
        Example: "sanjose now" -> ["sanjose now", "sanjose", "now"]
        """
        normalized = self._normalize_location_text(location_query)
        tokens = [tok for tok in re.split(r"[\s,]+", normalized) if tok]
        if not tokens:
            return [location_query.strip()]

        queries: List[str] = []

        def _push(q: str):
            q = q.strip()
            if q and q not in queries:
                queries.append(q)

        _push(" ".join(tokens))
        if len(tokens) > 1:
            for end in range(len(tokens) - 1, 0, -1):
                _push(" ".join(tokens[:end]))
            for start in range(1, len(tokens)):
                _push(" ".join(tokens[start:]))

        return queries[:max_queries]

    def _fetch_openweathermap_geocode(self, location_query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self._api_key:
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
        candidate_norm = self._normalize_location_text(candidate_query)
        original_norm = self._normalize_location_text(original_query)
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
            score += 0.06
        if country and country in original_compact:
            score += 0.04

        candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate_norm))
        display_tokens = set(re.findall(r"[a-z0-9]+", display))
        if city:
            display_tokens.add(city)

        if candidate_tokens:
            overlap = len(candidate_tokens & display_tokens) / len(candidate_tokens)
            score += 0.18 * overlap
            score -= 0.12 * (1.0 - overlap)

        score += max(0.0, 0.04 - (0.01 * variant_rank))
        return max(0.0, min(1.0, score))

    def resolve_location(self, location_query: str, original_query: str = "", limit: int = 5) -> Dict[str, Any]:
        """
        Resolve location text to a canonical, geocoded location.
        Returns one of: resolved, ambiguous, not_found, unavailable.
        """
        if not self._available:
            return {"status": "unavailable"}

        normalized_query = (location_query or "").strip()
        if not normalized_query or normalized_query == "Unknown":
            return {"status": "not_found", "query": location_query}

        query_variants = self._generate_location_queries(normalized_query)
        scored_candidates: List[Dict[str, Any]] = []

        for variant_rank, query_variant in enumerate(query_variants):
            if self._provider == "weatherapi":
                raw_candidates = self._fetch_weatherapi_geocode(query_variant, limit=limit)
            else:
                raw_candidates = self._fetch_openweathermap_geocode(query_variant, limit=limit)

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
            key = f"{round(candidate.get('lat') or 0, 4)}:{round(candidate.get('lon') or 0, 4)}:{candidate.get('display_name', '').lower()}"
            existing = deduped.get(key)
            if not existing or candidate["confidence"] > existing["confidence"]:
                deduped[key] = candidate

        ranked = sorted(deduped.values(), key=lambda x: x["confidence"], reverse=True)
        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None

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

    def get_forecast(self, location: str, days: int = 5) -> Optional[Dict[str, Any]]:
        """Fetch weather forecast for location."""
        if not self._available or not location or location == "Unknown":
            return None

        if self._provider != "weatherapi":
            print(f"[Weather] Forecast only available with WeatherAPI.com provider")
            return None

        print(f"[Weather] Fetching {days}-day forecast for {location}...")
        data = self._fetch_weatherapi_forecast(location, days)

        if data:
            print(f"[Weather] Forecast data retrieved ({data['forecast_days']} days)")

        return data

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

    def get_weather(self, location: str) -> Optional[Dict[str, Any]]:
        """Fetch current weather for location."""
        if not self._available or not location or location == "Unknown":
            return None

        cached = self._get_from_cache(location)
        if cached:
            print(f"[Weather] Using cached data for {location}")
            return cached

        print(f"[Weather] Fetching weather for {location}...")
        if self._provider == "weatherapi":
            data = self._fetch_weatherapi(location)
        else:
            data = self._fetch_openweathermap(location)

        if data:
            self._save_to_cache(location, data)
            print(f"[Weather] Weather data retrieved")

        return data

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

    return weather_service.format_for_llm(weather_data)


weather_tools = [get_weather_tool]
