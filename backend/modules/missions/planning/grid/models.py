from __future__ import annotations

import math
from dataclasses import dataclass

from backend.core.geometry.projection import lonlat_to_xy_m as _lonlat_to_xy_m
from backend.modules.missions.planning.grid.constants import (
    MAX_GRID_ROWS,
    MAX_GRID_ROUTE_M,
    MAX_GRID_WAYPOINTS,
)
from backend.modules.missions.planning.grid.geo import _poly_centroid_lonlat
from backend.modules.vehicle_runtime.types import Coordinate


@dataclass(frozen=True)
class GridPlanResult:
    waypoints: list[Coordinate]
    work_leg_mask: list[bool]  # len == len(waypoints) - 1
    angle_deg: float
    spacing_m: float
    stats: dict


def _coords_close(a: Coordinate, b: Coordinate, tol: float = 1e-7) -> bool:
    return abs(a.lat - b.lat) <= tol and abs(a.lon - b.lon) <= tol


def _route_length_m(
    waypoints: list[Coordinate],
    lon0: float,
    lat0: float,
) -> float:
    if len(waypoints) < 2:
        return 0.0
    xy = [_lonlat_to_xy_m(w.lon, w.lat, lon0, lat0) for w in waypoints]
    return float(sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(xy, xy[1:])))


def _validate_plan_limits(plan: GridPlanResult) -> None:
    rows = int(plan.stats.get("rows", 0))
    waypoints = len(plan.waypoints)
    route_m = float(plan.stats.get("route_m", 0.0) or 0.0)

    if rows > MAX_GRID_ROWS:
        raise ValueError(
            f"Grid has {rows} rows, exceeding the limit of {MAX_GRID_ROWS}. "
            "Increase row spacing, increase row stride, or split the field."
        )
    if waypoints > MAX_GRID_WAYPOINTS:
        raise ValueError(
            f"Grid has {waypoints} waypoints, exceeding the limit of {MAX_GRID_WAYPOINTS}. "
            "Increase row spacing, increase row stride, or split the field."
        )
    if route_m > MAX_GRID_ROUTE_M:
        raise ValueError(
            f"Grid route is {route_m:.1f} m, exceeding the limit of {MAX_GRID_ROUTE_M:.0f} m. "
            "Increase spacing/stride or divide the survey into multiple missions."
        )


def combine_grid_plans(
    plans: list[GridPlanResult],
    poly_lonlat: list[tuple[float, float]],
    pattern_mode: str,
) -> GridPlanResult:
    """Concatenate one or more grid plans into a single flyable route."""
    if not plans:
        raise ValueError("No grid plans to combine")

    combined_waypoints = list(plans[0].waypoints)
    combined_mask = list(plans[0].work_leg_mask)

    for plan in plans[1:]:
        if not plan.waypoints:
            continue

        first = plan.waypoints[0]
        if not combined_waypoints:
            combined_waypoints = list(plan.waypoints)
            combined_mask = list(plan.work_leg_mask)
            continue

        if not _coords_close(combined_waypoints[-1], first):
            combined_waypoints.append(first)
            combined_mask.append(False)  # transit connector between passes

        combined_waypoints.extend(plan.waypoints[1:])
        combined_mask.extend(plan.work_leg_mask)

    lon0, lat0 = _poly_centroid_lonlat(poly_lonlat)
    route_m = round(_route_length_m(combined_waypoints, lon0, lat0), 1)

    area_m2 = float(plans[0].stats.get("area_m2", 0.0))
    rows = sum(int(p.stats.get("rows", 0)) for p in plans)
    return GridPlanResult(
        waypoints=combined_waypoints,
        work_leg_mask=combined_mask,
        angle_deg=float(plans[0].angle_deg),
        spacing_m=float(plans[0].spacing_m),
        stats={
            "pattern_mode": pattern_mode,
            "passes": len(plans),
            "angles_deg": [round(float(p.angle_deg), 3) for p in plans],
            "rows": rows,
            "waypoints": len(combined_waypoints),
            "route_m": route_m,
            "area_m2": round(area_m2, 1),
        },
    )
