from __future__ import annotations

import math
from typing import Any

from backend.modules.patrol.planning import (
    generate_grid_surveillance_plan,
    generate_private_patrol_plan,
)
from backend.modules.property_patrol.models import PropertyPatrolSite, PropertyPatrolTemplate
from backend.modules.property_patrol.services.geometry import polygon_from_geojson, waypoint_dict
from backend.modules.vehicle_runtime.types import Coordinate


class PatrolRoutePlanner:
    def generate(
        self,
        *,
        site: PropertyPatrolSite,
        template: PropertyPatrolTemplate,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        safe_poly = polygon_from_geojson(site.flight_safe_area, name="flight_safe_area")
        ring_lonlat = [(float(x), float(y)) for x, y in list(safe_poly.exterior.coords)[:-1]]
        if template.patrol_mode == "grid":
            plan = generate_grid_surveillance_plan(
                ring_lonlat,
                altitude_agl_m=template.altitude_m,
                grid_spacing_m=template.grid_spacing_m,
                grid_angle_deg=0.0,
                safety_inset_m=max(0.0, template.boundary_offset_m),
            )
        elif template.patrol_mode == "adaptive":
            plan = generate_private_patrol_plan(
                ring_lonlat,
                altitude_agl_m=template.altitude_m,
                path_offset_m=template.boundary_offset_m,
                direction="clockwise",
                max_segment_length_m=25.0,
            )
            plan.stats["adaptive_priority"] = "recent_events_first_extension_point"
        else:
            plan = generate_private_patrol_plan(
                ring_lonlat,
                altitude_agl_m=template.altitude_m,
                path_offset_m=template.boundary_offset_m,
                direction="clockwise",
                max_segment_length_m=25.0,
            )
        waypoints = [
            waypoint_dict(
                wp.lat,
                wp.lon,
                wp.alt,
                speed_mps=template.speed_mps,
                camera_direction=template.camera_direction,
                gimbal_pitch_deg=template.camera_gimbal_pitch_deg,
            )
            for wp in plan.waypoints
        ]
        stats = dict(plan.stats)
        stats["estimated_duration_minutes"] = round(
            _route_length_m(plan.waypoints) / max(0.1, template.speed_mps) / 60.0,
            1,
        )
        return waypoints, stats


def _route_length_m(waypoints: list[Coordinate]) -> float:
    total = 0.0
    for a, b in zip(waypoints, waypoints[1:], strict=False):
        total += _distance_m(a.lat, a.lon, b.lat, b.lon)
    return total


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


route_planner = PatrolRoutePlanner()

