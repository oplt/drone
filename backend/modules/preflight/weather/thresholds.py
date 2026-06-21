from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.config.runtime import settings


@dataclass(frozen=True)
class WeatherThresholds:
    enabled: bool
    fail_policy: str
    wind_max_mps: float
    gust_max_mps: float
    max_precip_mm: float
    min_visibility_m: float
    max_cloud_cover_pct: float
    min_temp_c: float
    max_temp_c: float
    blocked_weather_codes: frozenset[int]
    warn_weather_codes: frozenset[int]
    kmi_validation_enabled: bool
    kmi_max_obs_age_hours: float
    kmi_wind_delta_warn_mps: float
    kmi_wind_delta_block_mps: float
    open_meteo_base_url: str
    kmi_wfs_base_url: str
    cache_ttl_s: float


def _parse_int_set(raw: str) -> frozenset[int]:
    values: set[int] = set()
    for chunk in str(raw or "").replace(" ", "").split(","):
        if not chunk:
            continue
        try:
            values.add(int(chunk))
        except ValueError:
            continue
    return frozenset(values)


def weather_thresholds_from_config(config: dict[str, Any] | None = None) -> WeatherThresholds:
    cfg = dict(config or {})
    get = cfg.get

    blocked_default = "45,48,56,57,65,67,75,77,82,85,86,95,96,99"
    warn_default = "51,53,55,61,63,80,81"

    return WeatherThresholds(
        enabled=bool(get("WEATHER_PREFLIGHT_ENABLED", settings.weather_preflight_enabled)),
        fail_policy=str(get("WEATHER_API_FAIL_POLICY", settings.weather_api_fail_policy)).lower(),
        wind_max_mps=float(get("WIND_MAX", settings.WIND_MAX)),
        gust_max_mps=float(get("GUST_MAX", settings.GUST_MAX)),
        max_precip_mm=float(get("WEATHER_MAX_PRECIP_MM", settings.weather_max_precip_mm)),
        min_visibility_m=float(get("WEATHER_MIN_VISIBILITY_M", settings.weather_min_visibility_m)),
        max_cloud_cover_pct=float(
            get("WEATHER_MAX_CLOUD_COVER_PCT", settings.weather_max_cloud_cover_pct)
        ),
        min_temp_c=float(get("WEATHER_MIN_TEMP_C", settings.weather_min_temp_c)),
        max_temp_c=float(get("WEATHER_MAX_TEMP_C", settings.weather_max_temp_c)),
        blocked_weather_codes=_parse_int_set(
            str(get("WEATHER_BLOCKED_CODES", settings.weather_blocked_codes))
        ),
        warn_weather_codes=_parse_int_set(
            str(get("WEATHER_WARN_CODES", settings.weather_warn_codes))
        ),
        kmi_validation_enabled=bool(
            get("KMI_RMI_VALIDATION_ENABLED", settings.kmi_rmi_validation_enabled)
        ),
        kmi_max_obs_age_hours=float(
            get("KMI_RMI_MAX_OBS_AGE_HOURS", settings.kmi_rmi_max_obs_age_hours)
        ),
        kmi_wind_delta_warn_mps=float(
            get("KMI_RMI_WIND_DELTA_WARN_MPS", settings.kmi_rmi_wind_delta_warn_mps)
        ),
        kmi_wind_delta_block_mps=float(
            get("KMI_RMI_WIND_DELTA_BLOCK_MPS", settings.kmi_rmi_wind_delta_block_mps)
        ),
        open_meteo_base_url=str(
            get("OPEN_METEO_BASE_URL", settings.open_meteo_base_url)
        ),
        kmi_wfs_base_url=str(get("KMI_RMI_WFS_BASE_URL", settings.kmi_rmi_wfs_base_url)),
        cache_ttl_s=float(get("WEATHER_CACHE_TTL_S", settings.weather_cache_ttl_s)),
    )
