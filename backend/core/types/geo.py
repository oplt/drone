from __future__ import annotations

import math
from typing import Any

from backend.modules.vehicle_runtime.types import Coordinate

EARTH_RADIUS_KM = 6371.0088


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _validate_lat_lon(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude out of range: {lat!r}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude out of range: {lon!r}")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    lat1 = _finite_float(lat1)
    lon1 = _finite_float(lon1)
    lat2 = _finite_float(lat2)
    lon2 = _finite_float(lon2)
    _validate_lat_lon(lat1, lon1)
    _validate_lat_lon(lat2, lon2)

    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    # Floating-point roundoff can make a slightly larger than 1.0 for antipodal points.
    a = max(0.0, min(1.0, a))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def coord_from_home(home: Any) -> Coordinate:
    # Accepts dronekit LocationGlobal/Relative or our Coordinate.
    lat = _finite_float(getattr(home, "lat", 0.0))
    lon = _finite_float(getattr(home, "lon", 0.0))
    alt = _finite_float(getattr(home, "alt", 0.0))
    _validate_lat_lon(lat, lon)
    return Coordinate(lat=lat, lon=lon, alt=alt)


def _total_mission_distance_km(home: Coordinate, start: Coordinate, end: Coordinate) -> float:
    d1 = haversine_km(home.lat, home.lon, start.lat, start.lon)
    d2 = haversine_km(start.lat, start.lon, end.lat, end.lon)
    d3 = haversine_km(end.lat, end.lon, home.lat, home.lon)
    return d1 + d2 + d3
