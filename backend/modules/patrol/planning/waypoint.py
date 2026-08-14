from __future__ import annotations

from collections.abc import Sequence

from backend.core.geometry.algorithm_runtime import profiled_geometry_plan
from backend.modules.patrol.planning.geometry import route_length_for_coords
from backend.modules.patrol.planning.models import PrivatePatrolPlan
from backend.modules.vehicle_runtime.types import Coordinate


@profiled_geometry_plan("waypoint_patrol_plan")
def generate_waypoint_patrol_plan(
    key_points_lonlat: Sequence[tuple[float, float]],
    *,
    altitude_agl_m: float,
    return_to_start: bool,
) -> PrivatePatrolPlan:
    """Build ordered key-point patrol route with optional return to first checkpoint."""
    if len(key_points_lonlat) < 2:
        raise ValueError("Waypoint patrol requires at least 2 key points")

    key_points: list[tuple[float, float]] = []
    for lon, lat in key_points_lonlat:
        lon_f = float(lon)
        lat_f = float(lat)
        if not (-180.0 <= lon_f <= 180.0 and -90.0 <= lat_f <= 90.0):
            raise ValueError("Invalid key point coordinates")
        key_points.append((lon_f, lat_f))

    route_points = list(key_points)
    if return_to_start and key_points and route_points[0] != route_points[-1]:
        route_points.append(route_points[0])

    waypoints = [
        Coordinate(lat=lat, lon=lon, alt=float(altitude_agl_m)) for lon, lat in route_points
    ]
    route_m = route_length_for_coords(waypoints)
    return PrivatePatrolPlan(
        waypoints=waypoints,
        stats={
            "task_type": "waypoint_patrol",
            "key_points": len(key_points),
            "waypoints": len(waypoints),
            "return_to_start": bool(return_to_start),
            "route_m": round(route_m, 1),
        },
    )
