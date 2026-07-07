from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx

from backend.modules.preflight.weather.location import haversine_m
from backend.modules.preflight.weather.models import WeatherSnapshot
from backend.modules.preflight.weather.coercion import to_float_or_none

logger = logging.getLogger(__name__)


async def enrich_with_kmi_rmi_observation(
    snapshot: WeatherSnapshot,
    *,
    wfs_base_url: str,
    max_obs_age_hours: float,
    timeout_s: float = 12.0,
) -> WeatherSnapshot:
    """Supplement Open-Meteo with nearest RMI AWS station observation (Belgium only)."""
    station = await _find_nearest_station(
        snapshot.latitude,
        snapshot.longitude,
        wfs_base_url=wfs_base_url,
        timeout_s=timeout_s,
    )
    if station is None:
        return snapshot

    observation = await _fetch_latest_station_observation(
        int(station["code"]),
        wfs_base_url=wfs_base_url,
        timeout_s=timeout_s,
        max_obs_age_hours=max_obs_age_hours,
    )
    if observation is None:
        return replace(
            snapshot,
            kmi_station_code=int(station["code"]),
            kmi_station_name=str(station.get("name") or ""),
            errors=snapshot.errors + ("KMI/RMI observation unavailable for nearest station",),
        )

    return replace(
        snapshot,
        kmi_station_code=int(station["code"]),
        kmi_station_name=str(station.get("name") or ""),
        kmi_wind_speed_mps=observation.get("wind_speed_mps"),
        kmi_wind_gust_mps=observation.get("wind_gust_mps"),
        kmi_observation_time=observation.get("timestamp"),
    )


async def _find_nearest_station(
    lat: float,
    lon: float,
    *,
    wfs_base_url: str,
    timeout_s: float,
) -> dict[str, Any] | None:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typenames": "aws:aws_station",
        "outputFormat": "application/json",
        "count": 200,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(wfs_base_url, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.info("KMI/RMI station lookup failed: %s", exc)
        return None

    nearest: dict[str, Any] | None = None
    nearest_dist = float("inf")
    for feature in payload.get("features") or []:
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        station_lon, station_lat = float(coords[0]), float(coords[1])
        dist = haversine_m(lat, lon, station_lat, station_lon)
        if dist < nearest_dist:
            nearest_dist = dist
            props = dict(feature.get("properties") or {})
            props["lat"] = station_lat
            props["lon"] = station_lon
            props["distance_m"] = dist
            nearest = props
    return nearest


async def _fetch_latest_station_observation(
    station_code: int,
    *,
    wfs_base_url: str,
    timeout_s: float,
    max_obs_age_hours: float,
) -> dict[str, Any] | None:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typenames": "aws:aws_10min",
        "outputFormat": "application/json",
        "count": 1,
        "sortBy": "timestamp D",
        "CQL_FILTER": f"code={station_code}",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(wfs_base_url, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.info("KMI/RMI observation fetch failed for code=%s: %s", station_code, exc)
        return None

    features = payload.get("features") or []
    if not features:
        return None

    props = features[0].get("properties") or {}
    ts_raw = props.get("timestamp")
    if not ts_raw:
        return None
    try:
        latest_ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=UTC)
    except ValueError:
        return None

    age_hours = (datetime.now(UTC) - latest_ts).total_seconds() / 3600.0
    if age_hours > max_obs_age_hours:
        logger.info(
            "KMI/RMI observation for code=%s is stale (%.1fh > %.1fh)",
            station_code,
            age_hours,
            max_obs_age_hours,
        )
        return None

    return {
        "timestamp": latest_ts.isoformat(),
        "wind_speed_mps": to_float_or_none(props.get("wind_speed_10m")),
        "wind_gust_mps": to_float_or_none(props.get("wind_gusts_speed")),
    }
