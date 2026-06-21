from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from backend.modules.preflight.weather.models import WeatherSnapshot

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
        wind_speed_mps=_to_float(current.get("wind_speed_10m")),
        wind_gust_mps=_to_float(current.get("wind_gusts_10m")),
        precipitation_mm=_to_float(current.get("precipitation")),
        visibility_m=_to_float(current.get("visibility")),
        weather_code=_to_int(current.get("weather_code")),
        temperature_c=_to_float(current.get("temperature_2m")),
        cloud_cover_pct=_to_float(current.get("cloud_cover")),
        fetched_at=time.time(),
    )


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
