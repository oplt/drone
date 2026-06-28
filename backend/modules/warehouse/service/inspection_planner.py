"""Semantic approach/hover/exit planning for inspection targets."""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.modules.warehouse.models import WarehouseScanTarget
from backend.modules.warehouse.planning.mission_stages import normalize_mission_stage
from backend.modules.warehouse.schemas import WarehouseInspectionWaypoint, WarehouseLocalPose


@dataclass(frozen=True)
class InspectionStagePolicy:
    approach_offset_m: float = 0.6
    exit_offset_m: float = 0.8


def _offset_pose(
    pose: WarehouseLocalPose, normal: dict | None, distance_m: float
) -> WarehouseLocalPose:
    if not isinstance(normal, dict):
        return pose
    values = [float(normal.get(axis, 0.0)) for axis in ("x", "y", "z")]
    length = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(length) or length <= 1e-9:
        return pose
    nx, ny, nz = (value / length for value in values)
    return pose.model_copy(
        update={
            "x_m": pose.x_m - nx * distance_m,
            "y_m": pose.y_m - ny * distance_m,
            "z_m": pose.z_m - nz * distance_m,
        }
    )


def semantic_target_waypoints(
    target: WarehouseScanTarget,
    *,
    hover_time_s: float,
    scan_timeout_s: float,
    metadata: dict[str, object],
    policy: InspectionStagePolicy = InspectionStagePolicy(),
    include_mission_legs: bool = True,
) -> list[WarehouseInspectionWaypoint]:
    pose = WarehouseLocalPose.model_validate(target.scan_pose_local_json)
    approach = _offset_pose(pose, target.shelf_normal_local_json, policy.approach_offset_m)
    exit_pose = _offset_pose(pose, target.shelf_normal_local_json, policy.exit_offset_m)
    legs: list[tuple[str, WarehouseLocalPose, float]] = []
    if include_mission_legs:
        legs.extend(
            [
                ("localize", approach, 0.0),
                ("staging", approach, 0.0),
                ("transit", approach, 0.0),
            ]
        )
    legs.extend(
        [
            ("approach_target", approach, 0.0),
            ("hover_for_scan", pose, hover_time_s),
            ("trigger_scan", pose, 0.0),
            ("exit_target", exit_pose, 0.0),
        ]
    )
    if include_mission_legs:
        legs.extend(
            [
                ("return", exit_pose, 0.0),
                ("land", exit_pose, 0.0),
            ]
        )
    return [
        WarehouseInspectionWaypoint(
            target_id=int(target.id),
            purpose=purpose,
            pose=stage_pose,
            hover_time_s=hover,
            scan_timeout_s=scan_timeout_s,
            metadata={
                **metadata,
                "semantic_stage": normalize_mission_stage(purpose),
                "legacy_stage": purpose,
            },
        )
        for purpose, stage_pose, hover in legs
    ]
