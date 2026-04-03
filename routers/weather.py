from fastapi import APIRouter, HTTPException
import requests

router = APIRouter(prefix="/api", tags=["weather"])

HEADERS = {
    "User-Agent": "OatmealFarmNetwork/1.0 (john@oatmealfarmnetwork.com)",
    "Accept": "application/geo+json",
}


def _parse_wind_mph(wind_str: str) -> float:
    """Parse NWS wind speed string like '5 mph' or '5 to 15 mph' → float."""
    try:
        return float(wind_str.split()[0])
    except Exception:
        return 0.0


@router.get("/weather")
def get_weather(lat: float, lon: float):
    """
    Fetch current conditions + hourly + 7-day forecast using api.weather.gov.
    No API key required — only a User-Agent header.
    Covers US locations only.
    """
    # ── Step 1: resolve lat/lon → NWS grid point ──────────────────────────────
    try:
        pts = requests.get(
            f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}",
            headers=HEADERS,
            timeout=10,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NWS unreachable: {e}")

    if pts.status_code == 404:
        raise HTTPException(status_code=404, detail="Location not covered by api.weather.gov (US only)")
    if pts.status_code != 200:
        raise HTTPException(status_code=502, detail=f"NWS points error {pts.status_code}")

    pts_props = pts.json()["properties"]
    city  = pts_props.get("relativeLocation", {}).get("properties", {}).get("city", "")
    state = pts_props.get("relativeLocation", {}).get("properties", {}).get("state", "")
    forecast_url = pts_props["forecast"]
    hourly_url   = pts_props["forecastHourly"]

    # ── Step 2: fetch forecast + hourly in parallel ────────────────────────────
    try:
        fc_resp = requests.get(forecast_url, headers=HEADERS, timeout=10)
        hr_resp = requests.get(hourly_url,   headers=HEADERS, timeout=10)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NWS forecast unreachable: {e}")

    # ── Step 3: build daily forecast (pair day + night periods) ───────────────
    daily = []
    today = {}
    if fc_resp.status_code == 200:
        periods = fc_resp.json()["properties"]["periods"]
        i = 0
        while i < len(periods) and len(daily) < 7:
            p = periods[i]
            if p["isDaytime"]:
                entry = {
                    "date":   p["startTime"][:10],
                    "high_f": p["temperature"],
                    "low_f":  None,
                    "icon":   p["icon"],
                    "condition": p["shortForecast"],
                }
                # pair with the following night period
                if i + 1 < len(periods) and not periods[i + 1]["isDaytime"]:
                    entry["low_f"] = periods[i + 1]["temperature"]
                    i += 2
                else:
                    i += 1
                daily.append(entry)
            else:
                # starts at night — grab low, no high
                entry = {
                    "date":   p["startTime"][:10],
                    "high_f": None,
                    "low_f":  p["temperature"],
                    "icon":   p["icon"],
                    "condition": p["shortForecast"],
                }
                daily.append(entry)
                i += 1

        if daily:
            today = {"high_f": daily[0]["high_f"], "low_f": daily[0]["low_f"]}

    # ── Step 4: build hourly + derive current from first hour ─────────────────
    hourly  = []
    current = {}
    if hr_resp.status_code == 200:
        hr_periods = hr_resp.json()["properties"]["periods"][:24]

        hourly = [
            {
                "time":   h["startTime"],
                "temp_f": h["temperature"],
                "icon":   h["icon"],
            }
            for h in hr_periods
        ]

        if hr_periods:
            first = hr_periods[0]
            current = {
                "temp_f":      first["temperature"],
                "feelslike_f": None,   # NWS standard forecast doesn't include feels-like
                "wind_mph":    _parse_wind_mph(first.get("windSpeed", "0 mph")),
                "wind_dir":    first.get("windDirection", ""),
                "humidity":    first.get("relativeHumidity", {}).get("value"),
                "condition":   first["shortForecast"],
                "icon":        first["icon"],
            }

    return {
        "location": {"city": city, "state": state},
        "current":  current,
        "today":    today,
        "hourly":   hourly,
        "daily":    daily,
    }
