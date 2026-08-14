from __future__ import annotations

import math
from typing import TYPE_CHECKING

from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

from backend.modules.warehouse.planning.local_planner.geometry import (
    _heading_deg,
    _normalize_angle_deg,
)
from backend.modules.warehouse.planning.local_planner.models import (
    WarehouseLocalPoint,
    WarehousePlanSegment,
)

if TYPE_CHECKING:
    pass

def _clip_segment_endpoints(
    start_xy: tuple[float, float],
    end_xy: tuple[float, float],
    trim_m: float,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    segment_len = math.hypot(end_xy[0] - start_xy[0], end_xy[1] - start_xy[1])
    if segment_len <= 0:
        return None
    if trim_m <= 0:
        return start_xy, end_xy
    if segment_len <= trim_m * 2.0:
        return None
    ux = (end_xy[0] - start_xy[0]) / segment_len
    uy = (end_xy[1] - start_xy[1]) / segment_len
    return (
        (start_xy[0] + ux * trim_m, start_xy[1] + uy * trim_m),
        (end_xy[0] - ux * trim_m, end_xy[1] - uy * trim_m),
    )


def _nearest_boundary_point(
    polygon: Polygon,
    target_xy: tuple[float, float],
) -> tuple[float, float]:
    boundary = polygon.exterior
    nearest = nearest_points(boundary, Point(target_xy))[0]
    return float(nearest.x), float(nearest.y)


def _point_towards(
    start_xy: tuple[float, float],
    target_xy: tuple[float, float],
    distance_m: float,
) -> tuple[float, float]:
    dx = float(target_xy[0]) - float(start_xy[0])
    dy = float(target_xy[1]) - float(start_xy[1])
    total = math.hypot(dx, dy)
    if total <= 1e-6:
        return start_xy
    scale = min(1.0, max(0.0, float(distance_m)) / total)
    return (
        float(start_xy[0]) + dx * scale,
        float(start_xy[1]) + dy * scale,
    )


def _dock_entry_points(
    *,
    footprint: Polygon,
    flyable_polygon: Polygon,
    first_scan_point: WarehouseLocalPoint,
    z_m: float,
    corridor_spacing_m: float,
    clearance_m: float,
) -> tuple[WarehouseLocalPoint, WarehouseLocalPoint]:
    target_xy = (float(first_scan_point.x_m), float(first_scan_point.y_m))
    dock_xy = _nearest_boundary_point(footprint, target_xy)
    flyable_edge_xy = _nearest_boundary_point(flyable_polygon, target_xy)
    staging_step_m = max(float(clearance_m) * 1.5, float(corridor_spacing_m) * 0.5, 0.75)
    staging_xy = _point_towards(flyable_edge_xy, target_xy, staging_step_m)
    dock_point = WarehouseLocalPoint(x_m=dock_xy[0], y_m=dock_xy[1], z_m=float(z_m))
    staging_point = WarehouseLocalPoint(
        x_m=float(staging_xy[0]),
        y_m=float(staging_xy[1]),
        z_m=float(z_m),
    )
    return dock_point, staging_point


def _segment_from_local_points(
    *,
    segment_id: str,
    start_point: WarehouseLocalPoint,
    end_point: WarehouseLocalPoint,
    leg_type: str,
    work_leg: bool,
    layer_index: int | None,
    corridor_id: str | None,
    source: str,
    yaw_deg: float | None = None,
) -> WarehousePlanSegment:
    return WarehousePlanSegment(
        segment_id=segment_id,
        local_start=start_point,
        local_end=end_point,
        work_leg=work_leg,
        leg_type=leg_type,
        yaw_deg=yaw_deg,
        layer_index=layer_index,
        corridor_id=corridor_id,
        source=source,
    )


def _perimeter_segments(
    *,
    flyable_polygon: Polygon,
    z_m: float,
    layer_index: int,
) -> list[WarehousePlanSegment]:
    ring = list(flyable_polygon.exterior.coords)
    if len(ring) >= 2 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return []

    points = [WarehouseLocalPoint(x_m=float(x), y_m=float(y), z_m=float(z_m)) for x, y in ring]
    segments: list[WarehousePlanSegment] = []
    for idx, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
        yaw = _normalize_angle_deg(_heading_deg((a.x_m, a.y_m), (b.x_m, b.y_m)))
        segments.append(
            WarehousePlanSegment(
                segment_id=f"perimeter_{layer_index}_{idx}",
                local_start=a,
                local_end=b,
                work_leg=True,
                leg_type="perimeter",
                yaw_deg=yaw,
                layer_index=layer_index,
                corridor_id=f"perimeter_{layer_index}",
                source="perimeter",
            )
        )
    return segments
