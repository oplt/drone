from __future__ import annotations

from collections.abc import Sequence

from backend.core.geometry.projection import (
    meters_per_deg_lat as _meters_per_deg_lat,
)
from backend.core.geometry.projection import (
    meters_per_deg_lon as _meters_per_deg_lon,
)
from backend.modules.patrol.geo import generate_orbit_offsets_m, max_orbit_radius_inside_polygon
from backend.modules.patrol.planning.geometry import route_length_for_coords
from backend.modules.patrol.planning.models import PrivatePatrolPlan
from backend.modules.vehicle_runtime.types import Coordinate


def generate_event_triggered_patrol_plan(
    event_location_lonlat: tuple[float, float],
    *,
    altitude_agl_m: float,
    verification_radius_m: float,
    geofence_polygon_lonlat: Sequence[tuple[float, float]] | None = None,
    safety_margin_m: float = 2.0,
    orbit_segments: int = 8,
) -> PrivatePatrolPlan:
    """Build a geofence-aware orbit verification pattern centered on the trigger."""
    lon = float(event_location_lonlat[0])
    lat = float(event_location_lonlat[1])
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise ValueError("Invalid trigger event location coordinates")

    requested_radius_m = max(0.0, float(verification_radius_m))
    radius_m = requested_radius_m
    if geofence_polygon_lonlat and len(geofence_polygon_lonlat) >= 3:
        radius_m = max_orbit_radius_inside_polygon(
            lon,
            lat,
            geofence_polygon_lonlat,
            requested_radius_m=requested_radius_m,
            safety_margin_m=float(safety_margin_m),
        )

    offsets_m: list[tuple[float, float]] = [(0.0, 0.0)]
    orbit_offsets = generate_orbit_offsets_m(
        radius_m,
        segments=int(orbit_segments),
        direction="clockwise",
    )
    if orbit_offsets:
        offsets_m.extend(orbit_offsets)
        offsets_m.append((0.0, 0.0))

    waypoints: list[Coordinate] = []
    for dx_m, dy_m in offsets_m:
        wp_lon = lon + (dx_m / _meters_per_deg_lon(lat))
        wp_lat = lat + (dy_m / _meters_per_deg_lat())
        waypoints.append(
            Coordinate(lat=float(wp_lat), lon=float(wp_lon), alt=float(altitude_agl_m))
        )

    route_m = route_length_for_coords(waypoints)
    return PrivatePatrolPlan(
        waypoints=waypoints,
        stats={
            "task_type": "event_triggered_patrol",
            "event_location_lonlat": [round(lon, 7), round(lat, 7)],
            "verification_radius_m": round(requested_radius_m, 2),
            "verification_radius_applied_m": round(radius_m, 2),
            "orbit_segments": len(orbit_offsets),
            "waypoints": len(waypoints),
            "verification_route_m": round(route_m, 1),
        },
    )
