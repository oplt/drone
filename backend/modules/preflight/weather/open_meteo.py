from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from backend.modules.preflight.weather.models import WeatherSnapshot
from backend.modules.preflight.weather.coercion import to_float_or_none, to_int_or_none

logger = logging.getLogger(__name__)

_CURRENT_FIELDS = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "precipitation",
    "weather_code",
    "visibility",
    "temperature_2m",
    "cloud_cover",
)


async def fetch_open_meteo_current(
    lat: float,
    lon: float,
    *,
    base_url: str,
    timeout_s: float = 8.0,
) -> WeatherSnapshot:
    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lon:.5f}",
        "current": ",".join(_CURRENT_FIELDS),
        "wind_speed_unit": "ms",
        "timezone": "GMT",
    }
    url = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()

    current = payload.get("current") or {}
    return WeatherSnapshot(
        latitude=float(payload.get("latitude", lat)),
        longitude=float(payload.get("longitude", lon)),
        source="open-meteo",
        wind_speed_mps=to_float_or_none(current.get("wind_speed_10m")),
        wind_gust_mps=to_float_or_none(current.get("wind_gusts_10m")),
        precipitation_mm=to_float_or_none(current.get("precipitation")),
        visibility_m=to_float_or_none(current.get("visibility")),
        weather_code=to_int_or_none(current.get("weather_code")),
        temperature_c=to_float_or_none(current.get("temperature_2m")),
        cloud_cover_pct=to_float_or_none(current.get("cloud_cover")),
        fetched_at=time.time(),
    )
