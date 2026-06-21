from __future__ import annotations

import logging
from typing import Any

from backend.modules.preflight.weather.cache import _weather_cache
from backend.modules.preflight.weather.kmi_rmi import enrich_with_kmi_rmi_observation
from backend.modules.preflight.weather.location import is_belgium_coordinates
from backend.modules.preflight.weather.models import WeatherSnapshot
from backend.modules.preflight.weather.open_meteo import fetch_open_meteo_current
from backend.modules.preflight.weather.thresholds import WeatherThresholds, weather_thresholds_from_config

logger = logging.getLogger(__name__)


async def fetch_weather_for_preflight(
    lat: float,
    lon: float,
    *,
    config: dict[str, Any] | None = None,
) -> tuple[WeatherSnapshot | None, str | None]:
    """Fetch and cache weather for outdoor preflight. Returns (snapshot, error)."""
    thresholds = weather_thresholds_from_config(config)
    if not thresholds.enabled:
        return None, "Weather preflight disabled"

    cached = await _weather_cache.get(lat, lon, ttl_s=thresholds.cache_ttl_s)
    if isinstance(cached, WeatherSnapshot):
        return cached, None

    try:
        snapshot = await fetch_open_meteo_current(
            lat,
            lon,
            base_url=thresholds.open_meteo_base_url,
        )
        if thresholds.kmi_validation_enabled and is_belgium_coordinates(lat, lon):
            snapshot = await enrich_with_kmi_rmi_observation(
                snapshot,
                wfs_base_url=thresholds.kmi_wfs_base_url,
                max_obs_age_hours=thresholds.kmi_max_obs_age_hours,
            )
        await _weather_cache.set(lat, lon, snapshot)
        return snapshot, None
    except Exception as exc:
        logger.warning("Weather fetch failed for lat=%s lon=%s: %s", lat, lon, exc)
        return None, str(exc)
