from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseScanTarget,
)
from backend.modules.warehouse.planning.indoor.local_navigation import LocalNavigationAdapter
from backend.modules.warehouse.planning.indoor.models import LocalPose
from backend.modules.warehouse.schemas import (
    WAREHOUSE_MAP_FRAME_ID,
    WarehouseInspectionWaypoint,
    WarehouseLocalPoint,
    WarehouseLocalPose,
    WarehouseShelfNormal,
)

logger = logging.getLogger(__name__)


def _normalize_yaw_deg(value: float) -> float:
    normalized = float(value) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def _pose_from_json(value: dict) -> WarehouseLocalPose:
    return WarehouseLocalPose.model_validate(value)


def compute_scan_pose(
    *,
    target_point: WarehouseLocalPoint,
    shelf_normal: WarehouseShelfNormal | None,
    standoff_m: float,
    yaw_deg: float | None = None,
) -> WarehouseLocalPose:
    """Return safe hover pose in front of target. Drone must fly here, not into target."""
    if shelf_normal is not None:
        length = math.sqrt(shelf_normal.x**2 + shelf_normal.y**2 + shelf_normal.z**2)
        nx = shelf_normal.x / length
        ny = shelf_normal.y / length
        nz = shelf_normal.z / length
        scan_x = float(target_point.x_m) - nx * float(standoff_m)
        scan_y = float(target_point.y_m) - ny * float(standoff_m)
        scan_z = float(target_point.z_m) - nz * float(standoff_m)
        yaw = math.degrees(
            math.atan2(
                float(target_point.y_m) - scan_y,
                float(target_point.x_m) - scan_x,
            )
        )
    else:
        scan_x = float(target_point.x_m)
        scan_y = float(target_point.y_m)
        scan_z = float(target_point.z_m)
        yaw = float(yaw_deg or 0.0)
    if yaw_deg is not None:
        yaw = float(yaw_deg)
    return WarehouseLocalPose(
        frame_id=target_point.frame_id or WAREHOUSE_MAP_FRAME_ID,
        x_m=scan_x,
        y_m=scan_y,
        z_m=scan_z,
        yaw_deg=_normalize_yaw_deg(yaw),
    )


def nearest_neighbor_targets(targets: list[WarehouseScanTarget]) -> list[WarehouseScanTarget]:
    if len(targets) <= 2:
        return targets
    remaining = list(targets)
    ordered = [remaining.pop(0)]
    while remaining:
        last_pose = _pose_from_json(ordered[-1].scan_pose_local_json)
        next_index = min(
            range(len(remaining)),
            key=lambda index: math.hypot(
                _pose_from_json(remaining[index].scan_pose_local_json).x_m - last_pose.x_m,
                _pose_from_json(remaining[index].scan_pose_local_json).y_m - last_pose.y_m,
            ),
        )
        ordered.append(remaining.pop(next_index))
    return ordered


def order_targets(
    targets: list[WarehouseScanTarget],
    *,
    optimize_order: bool,
) -> list[WarehouseScanTarget]:
    ordered = sorted(
        targets,
        key=lambda target: (
            int(target.priority),
            str(target.aisle_code or ""),
            str(target.rack_code or ""),
            int(target.shelf_level or 0),
            str(target.bin_code or ""),
            int(target.id),
        ),
    )
    if optimize_order:
        return nearest_neighbor_targets(ordered)
    return ordered


def build_inspection_waypoints(
    targets: list[WarehouseScanTarget],
    *,
    default_hover_time_s: float | None = None,
    default_scan_timeout_s: float | None = None,
) -> list[WarehouseInspectionWaypoint]:
    waypoints: list[WarehouseInspectionWaypoint] = []
    for target in targets:
        pose = _pose_from_json(target.scan_pose_local_json)
        hover_time_s = float(
            default_hover_time_s if default_hover_time_s is not None else target.hover_time_s
        )
        scan_timeout_s = float(
            default_scan_timeout_s
            if default_scan_timeout_s is not None
            else target.scan_timeout_s
        )
        base_metadata = {
            "aisle_code": target.aisle_code,
            "rack_code": target.rack_code,
            "bin_code": target.bin_code,
            "sku": target.sku,
            "barcode": target.barcode,
        }
        waypoints.extend(
            [
                WarehouseInspectionWaypoint(
                    target_id=int(target.id),
                    purpose="navigate_to_scan_pose",
                    pose=pose,
                    hover_time_s=0.0,
                    scan_timeout_s=scan_timeout_s,
                    metadata=base_metadata,
                ),
                WarehouseInspectionWaypoint(
                    target_id=int(target.id),
                    purpose="hover_for_scan",
                    pose=pose,
                    hover_time_s=hover_time_s,
                    scan_timeout_s=scan_timeout_s,
                    metadata=base_metadata,
                ),
                WarehouseInspectionWaypoint(
                    target_id=int(target.id),
                    purpose="trigger_barcode_scan",
                    pose=pose,
                    hover_time_s=0.0,
                    scan_timeout_s=scan_timeout_s,
                    metadata=base_metadata,
                ),
                WarehouseInspectionWaypoint(
                    target_id=int(target.id),
                    purpose="record_result",
                    pose=pose,
                    hover_time_s=0.0,
                    scan_timeout_s=scan_timeout_s,
                    metadata=base_metadata,
                ),
            ]
        )
    return waypoints


@dataclass(frozen=True)
class ScanResult:
    status: str
    detected_barcode: str | None = None
    confidence: float | None = None
    image_asset_id: int | None = None
    video_asset_id: int | None = None
    error_message: str | None = None


class WarehouseScanner(Protocol):
    async def scan_target(self, target: WarehouseScanTarget, timeout_s: float) -> ScanResult: ...


class MockWarehouseScanner:
    async def scan_target(self, target: WarehouseScanTarget, timeout_s: float) -> ScanResult:
        del timeout_s
        await asyncio.sleep(0)
        logger.info(
            "warehouse_inspection_scan_mock",
            extra={"target_id": int(target.id), "barcode": target.barcode},
        )
        return ScanResult(
            status="success" if target.barcode else "failed",
            detected_barcode=target.barcode,
            confidence=1.0 if target.barcode else 0.0,
            error_message=None if target.barcode else "Mock scanner has no expected barcode.",
        )


async def execute_inspection_mission(
    *,
    db: AsyncSession,
    mission: WarehouseInspectionMission,
    targets: list[WarehouseScanTarget],
    navigator: LocalNavigationAdapter,
    scanner: WarehouseScanner | None = None,
    speed_mps: float | None = None,
) -> None:
    scanner = scanner or MockWarehouseScanner()
    mission.status = "running"
    await db.flush()
    logger.info("warehouse_inspection_mission_started", extra={"mission_id": int(mission.id)})
    critical_failure = False
    for target in targets:
        pose_schema = _pose_from_json(target.scan_pose_local_json)
        pose = LocalPose(
            x_m=pose_schema.x_m,
            y_m=pose_schema.y_m,
            z_m=pose_schema.z_m,
            yaw_deg=pose_schema.yaw_deg,
            frame_id=pose_schema.frame_id,
        )
        logger.info(
            "warehouse_inspection_target_navigation_started",
            extra={"mission_id": int(mission.id), "target_id": int(target.id)},
        )
        try:
            await navigator.goto_local_pose(
                pose,
                speed_mps=speed_mps,
                timeout_s=max(10.0, float(target.scan_timeout_s)),
            )
            logger.info(
                "warehouse_inspection_target_reached",
                extra={"mission_id": int(mission.id), "target_id": int(target.id)},
            )
            await navigator.hold_position(timeout_s=float(target.hover_time_s))
            logger.info(
                "warehouse_inspection_scan_started",
                extra={"mission_id": int(mission.id), "target_id": int(target.id)},
            )
            scan = await scanner.scan_target(target, timeout_s=float(target.scan_timeout_s))
        except TimeoutError as exc:
            scan = ScanResult(status="timeout", error_message=str(exc))
        except Exception as exc:
            logger.exception(
                "warehouse_inspection_target_failed",
                extra={"mission_id": int(mission.id), "target_id": int(target.id)},
            )
            scan = ScanResult(status="failed", error_message=str(exc))

        result = WarehouseInspectionResult(
            mission_id=int(mission.id),
            target_id=int(target.id),
            status=scan.status,
            expected_barcode=target.barcode,
            detected_barcode=scan.detected_barcode,
            confidence=scan.confidence,
            image_asset_id=scan.image_asset_id,
            video_asset_id=scan.video_asset_id,
            drone_pose_local_json=pose_schema.model_dump(),
            error_message=scan.error_message,
            scanned_at=datetime.now(UTC),
        )
        db.add(result)
        await db.flush()
        logger.info(
            "warehouse_inspection_scan_result",
            extra={
                "mission_id": int(mission.id),
                "target_id": int(target.id),
                "status": scan.status,
            },
        )
    if bool(mission.return_to_dock):
        try:
            await navigator.land_on_dock(None)
        except Exception:
            critical_failure = True
            logger.exception(
                "warehouse_inspection_return_to_dock_failed",
                extra={"mission_id": int(mission.id)},
            )
    mission.status = "failed" if critical_failure else "completed"
    await db.flush()
    logger.info(
        "warehouse_inspection_mission_completed",
        extra={"mission_id": int(mission.id), "status": mission.status},
    )
