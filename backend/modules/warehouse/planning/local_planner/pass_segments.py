from __future__ import annotations

from backend.modules.warehouse.planning.local_planner.geometry import (
    _heading_deg,
    _normalize_angle_deg,
)
from backend.modules.warehouse.planning.local_planner.models import (
    WarehouseCorridor,
    WarehouseLocalPoint,
    WarehousePlanSegment,
)
from backend.modules.warehouse.planning.local_planner.types import WarehouseViewMode

def _with_z(
    point: WarehouseLocalPoint,
    *,
    z_m: float,
    yaw_deg: float | None = None,
) -> WarehouseLocalPoint:
    return WarehouseLocalPoint(
        x_m=float(point.x_m),
        y_m=float(point.y_m),
        z_m=float(z_m),
        yaw_deg=yaw_deg if yaw_deg is None else _normalize_angle_deg(yaw_deg),
    )


def _pass_segments_for_corridor(
    *,
    corridor: WarehouseCorridor,
    z_m: float,
    layer_index: int,
    view_mode: WarehouseViewMode,
    reverse: bool,
) -> list[WarehousePlanSegment]:
    base_start = corridor.end if reverse else corridor.start
    base_end = corridor.start if reverse else corridor.end
    heading = _normalize_angle_deg(
        _heading_deg((base_start.x_m, base_start.y_m), (base_end.x_m, base_end.y_m))
    )

    def _segment(
        *,
        segment_id: str,
        start_point: WarehouseLocalPoint,
        end_point: WarehouseLocalPoint,
        yaw_deg: float | None,
    ) -> WarehousePlanSegment:
        local_start = _with_z(start_point, z_m=z_m, yaw_deg=yaw_deg)
        local_end = _with_z(end_point, z_m=z_m, yaw_deg=yaw_deg)
        return WarehousePlanSegment(
            segment_id=segment_id,
            local_start=local_start,
            local_end=local_end,
            work_leg=True,
            leg_type="scan",
            yaw_deg=yaw_deg,
            layer_index=layer_index,
            corridor_id=corridor.corridor_id,
            source=corridor.source,
        )

    if view_mode == "dual_face":
        left_yaw = _normalize_angle_deg(heading + 90.0)
        right_yaw = _normalize_angle_deg(heading - 90.0)
        return [
            _segment(
                segment_id=f"{corridor.corridor_id}_layer_{layer_index}_left",
                start_point=base_start,
                end_point=base_end,
                yaw_deg=left_yaw,
            ),
            _segment(
                segment_id=f"{corridor.corridor_id}_layer_{layer_index}_right",
                start_point=base_end,
                end_point=base_start,
                yaw_deg=right_yaw,
            ),
        ]

    if view_mode == "left_face":
        yaw = _normalize_angle_deg(heading + 90.0)
    elif view_mode == "right_face":
        yaw = _normalize_angle_deg(heading - 90.0)
    else:
        yaw = heading

    return [
        _segment(
            segment_id=f"{corridor.corridor_id}_layer_{layer_index}",
            start_point=base_start,
            end_point=base_end,
            yaw_deg=yaw,
        )
    ]
