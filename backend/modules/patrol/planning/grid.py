from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from backend.core.geometry.algorithm_runtime import profiled_geometry_plan
from backend.modules.missions.planning.grid import GridPlanner, _validate_plan_limits
from backend.modules.patrol.planning.models import PrivatePatrolPlan
from backend.modules.vehicle_runtime.types import Coordinate


@profiled_geometry_plan("grid_surveillance_plan")
def generate_grid_surveillance_plan(
    polygon_lonlat: Sequence[tuple[float, float]],
    *,
    altitude_agl_m: float,
    grid_spacing_m: float,
    grid_angle_deg: float,
    safety_inset_m: float,
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon",
    crosshatch_angle_offset_deg: float = 90.0,
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine",
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto",
    row_stride: int = 1,
    row_phase_m: float = 0.0,
) -> PrivatePatrolPlan:
    """Build a coverage grid plan for large-area private surveillance."""
    if len(polygon_lonlat) < 3:
        raise ValueError("Grid surveillance requires a polygon with at least 3 vertices")
    spacing = float(grid_spacing_m)
    if spacing <= 0:
        raise ValueError("grid_spacing_m must be > 0")

    poly = [(float(lon), float(lat)) for lon, lat in polygon_lonlat]
    plan = GridPlanner.generate(
        poly,
        spacing_m=spacing,
        angle_deg=float(grid_angle_deg),
        inset_m=max(0.0, float(safety_inset_m)),
        lane_strategy=lane_strategy,
        start_corner=start_corner,
        row_stride=max(1, int(row_stride)),
        row_phase_m=max(0.0, float(row_phase_m)),
    )
    _validate_plan_limits(plan)
    plan_waypoints = list(plan.waypoints)
    stats = dict(plan.stats)
    if pattern_mode == "crosshatch":
        plan2 = GridPlanner.generate(
            poly,
            spacing_m=spacing,
            angle_deg=(float(grid_angle_deg) + float(crosshatch_angle_offset_deg)) % 180.0,
            inset_m=max(0.0, float(safety_inset_m)),
            lane_strategy=lane_strategy,
            start_corner=start_corner,
            row_stride=max(1, int(row_stride)),
            row_phase_m=max(0.0, float(row_phase_m)),
        )
        _validate_plan_limits(plan2)
        plan_waypoints.extend(plan2.waypoints)
        stats["rows"] = int(stats.get("rows", 0) or 0) + int(plan2.stats.get("rows", 0) or 0)
        stats["waypoints"] = len(plan_waypoints)
        stats["route_m"] = round(
            float(stats.get("route_m", 0.0) or 0.0) + float(plan2.stats.get("route_m", 0.0) or 0.0),
            1,
        )

    waypoints = [
        Coordinate(lat=float(wp.lat), lon=float(wp.lon), alt=float(altitude_agl_m))
        for wp in plan_waypoints
    ]
    return PrivatePatrolPlan(
        waypoints=waypoints,
        stats={
            "task_type": "grid_surveillance",
            "rows": int(stats.get("rows", 0)),
            "waypoints": len(waypoints),
            "route_m": round(float(stats.get("route_m", 0.0) or 0.0), 1),
            "area_m2": round(float(stats.get("area_m2", 0.0) or 0.0), 1),
            "grid_spacing_m": round(float(plan.spacing_m), 2),
            "grid_angle_deg": round(float(plan.angle_deg), 2),
            "pattern_mode": pattern_mode,
            "crosshatch_angle_offset_deg": round(float(crosshatch_angle_offset_deg), 2),
            "safety_inset_m": round(float(safety_inset_m), 2),
            "lane_strategy": lane_strategy,
            "start_corner": start_corner,
            "row_stride": max(1, int(row_stride)),
            "row_phase_m": round(max(0.0, float(row_phase_m)), 2),
        },
    )
