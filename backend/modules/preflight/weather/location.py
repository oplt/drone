from __future__ import annotations

import math
from typing import Any

from backend.modules.missions.flight_profile import INDOOR_MISSION_TYPES
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.warehouse.service.warehouse_preflight import uses_warehouse_ros_preflight


def is_outdoor_preflight_mission(mission_type: str | None) -> bool:
    """Return True when standard outdoor MAVLink preflight (incl. weather) applies."""
    if not mission_type:
        return True
    normalized = str(mission_type).strip().lower()
    if uses_warehouse_ros_preflight(normalized):
        return False
    if normalized in INDOOR_MISSION_TYPES:
        return False
    if normalized == MissionType.WAREHOUSE_INSPECTION.value:
        return False
    return True


def is_belgium_coordinates(lat: float, lon: float) -> bool:
    """Approximate Belgium bounding box for KMI/RMI supplemental validation."""
    return 49.4 <= lat <= 51.6 and 2.4 <= lon <= 6.5


def _telemetry_lat_lon(vehicle_state: Any) -> tuple[float, float] | None:
    if isinstance(vehicle_state, dict):
        lat = vehicle_state.get("lat") or vehicle_state.get("latitude")
        lon = vehicle_state.get("lon") or vehicle_state.get("longitude")
    else:
        lat = getattr(vehicle_state, "lat", None) or getattr(vehicle_state, "latitude", None)
        lon = getattr(vehicle_state, "lon", None) or getattr(vehicle_state, "longitude", None)
    try:
        if lat is None or lon is None:
            return None
        lat_f, lon_f = float(lat), float(lon)
        if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
            return None
        if abs(lat_f) < 1e-6 and abs(lon_f) < 1e-6:
            return None
        return lat_f, lon_f
    except (TypeError, ValueError):
        return None


def _waypoint_lat_lon(point: Any) -> tuple[float, float] | None:
    try:
        if isinstance(point, dict):
            if "lat" in point and "lon" in point:
                return float(point["lat"]), float(point["lon"])
            if "latitude" in point and "longitude" in point:
                return float(point["latitude"]), float(point["longitude"])
        if hasattr(point, "lat") and hasattr(point, "lon"):
            return float(point.lat), float(point.lon)
    except (TypeError, ValueError):
        return None
    return None


def _geofence_centroid(geofence_polygon: list[Any] | None) -> tuple[float, float] | None:
    if not geofence_polygon:
        return None
    coords = [_waypoint_lat_lon(pt) for pt in geofence_polygon]
    coords = [c for c in coords if c is not None]
    if not coords:
        return None
    lat = sum(c[0] for c in coords) / len(coords)
    lon = sum(c[1] for c in coords) / len(coords)
    return lat, lon


def _mission_centroid(mission: Any) -> tuple[float, float] | None:
    waypoints = list(getattr(mission, "waypoints", []) or [])
    if waypoints:
        first = _waypoint_lat_lon(waypoints[0])
        if first is not None:
            return first
    polygon = getattr(mission, "polygon", None)
    if polygon:
        return _geofence_centroid(list(polygon))
    field_polygon = getattr(mission, "geofence_polygon_lonlat", None)
    if field_polygon:
        return _geofence_centroid(list(field_polygon))
    return None


def resolve_preflight_coordinates(
    vehicle_state: Any,
    mission: Any,
    *,
    geofence_polygon: list[Any] | None = None,
) -> tuple[float, float] | None:
    """Best-effort GPS location for outdoor weather lookup."""
    for candidate in (
        _telemetry_lat_lon(vehicle_state),
        _mission_centroid(mission),
        _geofence_centroid(geofence_polygon),
    ):
        if candidate is not None:
            return candidate
    return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
