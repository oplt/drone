from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseCoordinateFrame,
    WarehouseDockStation,
    WarehouseInspectionMission,
    WarehouseInspectionValidationResult,
    WarehouseLayoutVersion,
    WarehouseMap,
    WarehouseModel,
    WarehouseScanTarget,
)
from backend.modules.warehouse.planning.indoor.models import LocalPose
from backend.modules.warehouse.service.coordinate_frames import transform_warehouse_points
from backend.modules.warehouse.service.drift_guard import validate_localization_evidence
from backend.modules.warehouse.service.esdf_inspection_validation import (
    esdf_points_from_structure_readiness,
    validate_inspection_path_esdf,
)
from backend.modules.warehouse.service.inspection_validation import validate_inspection_path
from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
    observe_inspection_validation,
    record_mission_rejection,
)
from backend.modules.warehouse.service.live_map_readiness import refresh_structure_input_readiness
from backend.modules.warehouse.service.occupancy_grid_parser import occupancy_grid_from_ros_yaml


@dataclass(frozen=True)
class MissionRevisionPins:
    layout_version_id: int
    layout_version: int
    map_model_id: int
    map_model_version: int
    validation_result_id: int
    artifact_checksums: dict[str, str]


def _input_checksum(
    *,
    target_ids: list[int],
    frame_id: int,
    layout_id: int,
    model_id: int,
    artifacts: dict[str, str],
) -> str:
    payload = {
        "target_ids": target_ids,
        "coordinate_frame_id": frame_id,
        "layout_version_id": layout_id,
        "map_model_id": model_id,
        "artifact_checksums": artifacts,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def create_mission_revision_pins(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    coordinate_frame_id: int,
    targets: list[WarehouseScanTarget],
    return_to_dock: bool,
    battery_pct: float = 100.0,
) -> MissionRevisionPins:
    layout_ids = {target.layout_version_id for target in targets}
    if None in layout_ids or len(layout_ids) != 1:
        raise HTTPException(409, "All scan targets must use one pinned warehouse layout")
    layout_id = int(next(iter(layout_ids)))
    layout = await db.get(WarehouseLayoutVersion, layout_id)
    if layout is None or layout.warehouse_map_id != warehouse_map_id or layout.status != "locked":
        record_mission_rejection(reason="layout_not_locked")
        raise HTTPException(409, "Scan target layout is not the locked warehouse layout")
    if layout.coordinate_frame_id != coordinate_frame_id or layout.map_model_id is None:
        raise HTTPException(409, "Locked layout has incomplete or stale revision provenance")
    model = await db.get(WarehouseModel, int(layout.map_model_id))
    if model is None or model.warehouse_map_id != warehouse_map_id:
        raise HTTPException(409, "Locked layout map model is unavailable")
    assets = (
        (await db.execute(select(WarehouseAsset).where(WarehouseAsset.model_id == model.id)))
        .scalars()
        .all()
    )
    unchecked = [int(asset.id) for asset in assets if not asset.checksum]
    if unchecked:
        raise HTTPException(409, f"Map model has artifacts without checksums: {unchecked}")
    artifacts = {str(asset.id): str(asset.checksum) for asset in assets if asset.checksum}
    if not artifacts:
        raise HTTPException(409, "Map model has no checksummed artifacts")
    target_ids = [int(target.id) for target in targets]

    readiness = await refresh_structure_input_readiness(timeout_s=5.0)
    grid = occupancy_grid_from_ros_yaml(readiness.occupancy_message)
    if grid is None:
        raise HTTPException(412, "Fresh occupancy/ESDF evidence is required for mission planning")
    message = readiness.occupancy_message or {}
    header = message.get("header") if isinstance(message, dict) else None
    grid_frame = str(header.get("frame_id") or "") if isinstance(header, dict) else ""
    warehouse_poses = [
        LocalPose(
            x_m=float(target.scan_pose_local_json["x_m"]),
            y_m=float(target.scan_pose_local_json["y_m"]),
            z_m=float(target.scan_pose_local_json["z_m"]),
            frame_id="warehouse_map",
        )
        for target in targets
    ]
    frame = await db.get(WarehouseCoordinateFrame, coordinate_frame_id)
    if frame is None:
        raise HTTPException(409, "Pinned coordinate frame is unavailable")

    def to_grid_pose(pose: LocalPose) -> LocalPose:
        if grid_frame == "warehouse_map":
            return pose
        if grid_frame != "odom":
            raise HTTPException(412, f"Unsupported occupancy frame: {grid_frame or 'missing'}")
        transformed = transform_warehouse_points(
            np.array([[pose.x_m, pose.y_m, pose.z_m]]), frame.transform_json
        )[0]
        return LocalPose(
            x_m=float(transformed[0]),
            y_m=float(transformed[1]),
            z_m=float(transformed[2]),
            frame_id="odom",
        )

    grid_poses = [to_grid_pose(pose) for pose in warehouse_poses]
    dock_ids = {target.dock_station_id for target in targets if target.dock_station_id is not None}
    start_grid_pose = None
    if len(dock_ids) == 1:
        dock = await db.get(WarehouseDockStation, int(next(iter(dock_ids))))
        if dock is not None and dock.warehouse_map_id == warehouse_map_id:
            raw = dock.exit_pose_local_json
            start_grid_pose = to_grid_pose(
                LocalPose(
                    x_m=float(raw["x_m"]),
                    y_m=float(raw["y_m"]),
                    z_m=float(raw["z_m"]),
                    frame_id="warehouse_map",
                )
            )
    warehouse_map = await db.get(WarehouseMap, warehouse_map_id)
    polygon = (
        warehouse_map.meta_data.get("polygon_local_m", [])
        if warehouse_map is not None and isinstance(warehouse_map.meta_data, dict)
        else []
    )
    with observe_inspection_validation():
        report = validate_inspection_path(
            targets=targets,
            grid=grid,
            grid_poses=grid_poses,
            warehouse_poses=warehouse_poses,
            warehouse_polygon=polygon,
            map_age_s=0.0,
            start_grid_pose=start_grid_pose,
            return_to_dock=return_to_dock,
            battery_pct=battery_pct,
        )
    esdf_points = esdf_points_from_structure_readiness(readiness)
    esdf_report = validate_inspection_path_esdf(
        poses=warehouse_poses,
        esdf_points_xyz=esdf_points,
        grid=grid,
        grid_poses=grid_poses,
    )
    for warning in esdf_report.get("warnings", []):
        if isinstance(warning, dict):
            report.warn(
                str(warning.get("check") or "esdf"),
                str(warning.get("message") or "ESDF warning"),
            )
    for failure in esdf_report.get("failures", []):
        if isinstance(failure, dict):
            report.fail(
                str(failure.get("check") or "esdf"),
                str(failure.get("message") or "ESDF validation failed"),
                **{k: v for k, v in failure.items() if k not in {"check", "message"}},
            )
    if not report.passed:
        record_mission_rejection(reason="inspection_validation_failed")
        raise HTTPException(
            412, {"message": "Inspection path validation failed", **report.to_dict()}
        )
    validation = WarehouseInspectionValidationResult(
        warehouse_map_id=warehouse_map_id,
        coordinate_frame_id=coordinate_frame_id,
        layout_version_id=layout_id,
        map_model_id=int(model.id),
        input_checksum=_input_checksum(
            target_ids=target_ids,
            frame_id=coordinate_frame_id,
            layout_id=layout_id,
            model_id=int(model.id),
            artifacts=artifacts,
        ),
        status="passed",
        result_json={
            "kind": "inspection_path_v1",
            "target_ids": target_ids,
            "occupancy_topic": readiness.occupancy_topic,
            "validated_at": datetime.now(UTC).isoformat(),
            **report.to_dict(),
        },
    )
    db.add(validation)
    await db.flush()
    return MissionRevisionPins(
        layout_id,
        int(layout.version),
        int(model.id),
        int(model.version),
        int(validation.id),
        artifacts,
    )


async def verify_mission_revision_pins(
    db: AsyncSession, mission: WarehouseInspectionMission
) -> None:
    required = (
        mission.coordinate_frame_id,
        mission.layout_version_id,
        mission.map_model_id,
        mission.validation_result_id,
    )
    if any(value is None for value in required):
        raise HTTPException(409, "Legacy mission has no complete immutable revision lock")
    layout = await db.get(WarehouseLayoutVersion, int(mission.layout_version_id))
    frame = await db.get(WarehouseCoordinateFrame, int(mission.coordinate_frame_id))
    model = await db.get(WarehouseModel, int(mission.map_model_id))
    validation = await db.get(
        WarehouseInspectionValidationResult, int(mission.validation_result_id)
    )
    if frame is None or frame.status != "locked" or frame.id != mission.coordinate_frame_id:
        raise HTTPException(409, "Mission coordinate revision is unavailable or superseded")
    try:
        evidence = validate_localization_evidence(
            transform=frame.transform_json,
            transform_timestamp=frame.transform_timestamp,
            max_age_s=float(frame.max_age_s),
            covariance=list(frame.covariance_json or []),
            confidence=float(frame.confidence or 0.0),
        )
    except ValueError as exc:
        raise HTTPException(409, f"Mission coordinate localization is unsafe: {exc}") from exc
    if frame.transform_checksum != evidence["checksum_sha256"]:
        raise HTTPException(409, "Mission coordinate transform checksum no longer matches")
    if (
        layout is None
        or layout.status != "locked"
        or layout.coordinate_frame_id != mission.coordinate_frame_id
    ):
        raise HTTPException(409, "Mission warehouse layout revision is stale")
    if (
        model is None
        or layout.map_model_id != model.id
        or model.coordinate_frame_id != mission.coordinate_frame_id
    ):
        raise HTTPException(409, "Mission map model revision is stale")
    if validation is None or validation.status != "passed":
        raise HTTPException(409, "Mission validation result is unavailable or failed")
    created_at = validation.created_at
    if created_at is None or (datetime.now(UTC) - created_at).total_seconds() > 10.0:
        raise HTTPException(409, "Mission path validation is stale; re-plan against the live map")
    pinned = dict(mission.artifact_checksums_json or {})
    assets = (
        (await db.execute(select(WarehouseAsset).where(WarehouseAsset.model_id == model.id)))
        .scalars()
        .all()
    )
    current = {str(asset.id): str(asset.checksum) for asset in assets if str(asset.id) in pinned}
    if not pinned or current != pinned:
        raise HTTPException(409, "Mission map artifact checksums no longer match")


def is_legacy_mission(mission: WarehouseInspectionMission) -> bool:
    """Legacy missions predate immutable frame/layout/model/validation pins."""
    return any(
        value is None
        for value in (
            mission.coordinate_frame_id,
            mission.layout_version_id,
            mission.map_model_id,
            mission.validation_result_id,
        )
    )


def require_legacy_same_origin_confirmation(
    mission: WarehouseInspectionMission, *, same_origin_confirmed: bool
) -> None:
    if is_legacy_mission(mission) and not same_origin_confirmed:
        raise HTTPException(
            409,
            detail={
                "code": "legacy_mission_non_repeatable",
                "message": (
                    "Legacy mission has no immutable coordinate revision. "
                    "Confirm the same physical takeoff origin explicitly or create a new mission."
                ),
            },
        )
