from __future__ import annotations

from collections.abc import Iterable

from shapely.geometry import LineString, Polygon

from backend.modules.warehouse.planning.local_planner.geometry import _points_close
from backend.modules.warehouse.planning.local_planner.models import (
    WarehouseKeepoutZone,
    WarehouseObstacleBox,
    WarehousePlanSegment,
)

def _append_segment_route(
    *,
    route_segments: list[WarehousePlanSegment],
    new_segments: Iterable[WarehousePlanSegment],
) -> None:
    for segment in new_segments:
        if route_segments and not _points_close(
            route_segments[-1].local_end,
            segment.local_start,
        ):
            transit = WarehousePlanSegment(
                segment_id=f"transit_{len(route_segments)}",
                local_start=route_segments[-1].local_end,
                local_end=segment.local_start,
                work_leg=False,
                leg_type="transit",
                yaw_deg=None,
                layer_index=segment.layer_index,
                corridor_id=segment.corridor_id,
                source="connector",
            )
            route_segments.append(transit)
        route_segments.append(segment)


def _segment_intersects_keepout(
    segment: WarehousePlanSegment,
    zone: WarehouseKeepoutZone,
) -> bool:
    if len(zone.footprint) < 3:
        return False
    min_z = float(zone.min_z_m) if zone.min_z_m is not None else None
    max_z = float(zone.max_z_m) if zone.max_z_m is not None else None
    seg_min_z = min(float(segment.local_start.z_m), float(segment.local_end.z_m))
    seg_max_z = max(float(segment.local_start.z_m), float(segment.local_end.z_m))
    if min_z is not None and seg_max_z < min_z:
        return False
    if max_z is not None and seg_min_z > max_z:
        return False
    line = LineString(
        [
            (float(segment.local_start.x_m), float(segment.local_start.y_m)),
            (float(segment.local_end.x_m), float(segment.local_end.y_m)),
        ]
    )
    poly = Polygon(zone.footprint)
    return line.intersects(poly)


def _segment_intersects_obstacle(
    segment: WarehousePlanSegment,
    obstacle: WarehouseObstacleBox,
) -> bool:
    half_x = float(obstacle.size_x_m) / 2.0
    half_y = float(obstacle.size_y_m) / 2.0
    min_z = float(obstacle.center.z_m) - (float(obstacle.size_z_m) / 2.0)
    max_z = float(obstacle.center.z_m) + (float(obstacle.size_z_m) / 2.0)
    seg_min_z = min(float(segment.local_start.z_m), float(segment.local_end.z_m))
    seg_max_z = max(float(segment.local_start.z_m), float(segment.local_end.z_m))
    if seg_max_z < min_z or seg_min_z > max_z:
        return False
    line = LineString(
        [
            (float(segment.local_start.x_m), float(segment.local_start.y_m)),
            (float(segment.local_end.x_m), float(segment.local_end.y_m)),
        ]
    )
    box = Polygon(
        [
            (float(obstacle.center.x_m) - half_x, float(obstacle.center.y_m) - half_y),
            (float(obstacle.center.x_m) + half_x, float(obstacle.center.y_m) - half_y),
            (float(obstacle.center.x_m) + half_x, float(obstacle.center.y_m) + half_y),
            (float(obstacle.center.x_m) - half_x, float(obstacle.center.y_m) + half_y),
        ]
    )
    return line.intersects(box)
