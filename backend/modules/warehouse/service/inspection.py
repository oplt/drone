from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

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
_MIN_NORMAL_LENGTH = 1e-9
_MIN_TIMEOUT_S = 0.1


def _normalize_yaw_deg(value: float) -> float:
    normalized = float(value) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def _pose_from_json(value: dict[str, Any]) -> WarehouseLocalPose:
    return WarehouseLocalPose.model_validate(value)


def _safe_float(value: Any, *, default: float, minimum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if not math.isfinite(parsed):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _target_id(target: WarehouseScanTarget) -> int:
    return _safe_int(getattr(target, "id", 0), default=0)


def _target_scan_timeout_s(target: WarehouseScanTarget) -> float:
    return _safe_float(
        getattr(target, "scan_timeout_s", 10.0), default=10.0, minimum=_MIN_TIMEOUT_S
    )


def _target_hover_time_s(target: WarehouseScanTarget) -> float:
    return _safe_float(getattr(target, "hover_time_s", 0.0), default=0.0, minimum=0.0)


def _metadata_for_target(target: WarehouseScanTarget) -> dict[str, Any]:
    return {
        "aisle_code": target.aisle_code,
        "rack_code": target.rack_code,
        "bin_code": target.bin_code,
        "sku": target.sku,
        "barcode": target.barcode,
    }


def _local_pose_from_schema(pose_schema: WarehouseLocalPose) -> LocalPose:
    return LocalPose(
        x_m=pose_schema.x_m,
        y_m=pose_schema.y_m,
        z_m=pose_schema.z_m,
        yaw_deg=pose_schema.yaw_deg,
        frame_id=pose_schema.frame_id,
    )


def compute_scan_pose(
    *,
    target_point: WarehouseLocalPoint,
    shelf_normal: WarehouseShelfNormal | None,
    standoff_m: float,
    yaw_deg: float | None = None,
) -> WarehouseLocalPose:
    """Return safe hover pose in front of target. Drone must fly here, not into target."""
    standoff = float(standoff_m)
    if not math.isfinite(standoff) or standoff < 0:
        raise ValueError("standoff_m must be a finite non-negative number")

    target_x = float(target_point.x_m)
    target_y = float(target_point.y_m)
    target_z = float(target_point.z_m)
    if not all(math.isfinite(value) for value in (target_x, target_y, target_z)):
        raise ValueError("target_point coordinates must be finite numbers")

    if shelf_normal is not None:
        nx_raw = float(shelf_normal.x)
        ny_raw = float(shelf_normal.y)
        nz_raw = float(shelf_normal.z)
        length = math.sqrt(nx_raw * nx_raw + ny_raw * ny_raw + nz_raw * nz_raw)
        if not math.isfinite(length) or length <= _MIN_NORMAL_LENGTH:
            raise ValueError("shelf_normal must be a non-zero finite vector")

        nx = nx_raw / length
        ny = ny_raw / length
        nz = nz_raw / length
        scan_x = target_x - nx * standoff
        scan_y = target_y - ny * standoff
        scan_z = target_z - nz * standoff
        yaw = math.degrees(math.atan2(target_y - scan_y, target_x - scan_x))
    else:
        scan_x = target_x
        scan_y = target_y
        scan_z = target_z
        yaw = float(yaw_deg or 0.0)

    if yaw_deg is not None:
        yaw = float(yaw_deg)
    if not math.isfinite(yaw):
        raise ValueError("yaw_deg must be finite when provided")

    return WarehouseLocalPose(
        frame_id=target_point.frame_id or WAREHOUSE_MAP_FRAME_ID,
        x_m=scan_x,
        y_m=scan_y,
        z_m=scan_z,
        yaw_deg=_normalize_yaw_deg(yaw),
    )


def nearest_neighbor_targets(targets: list[WarehouseScanTarget]) -> list[WarehouseScanTarget]:
    """Greedy nearest-neighbor ordering with one pose parse per target.

    The original implementation reparsed Pydantic pose models inside the inner
    loop, turning every comparison into repeated validation work. This keeps the
    public behavior while removing repeated pure computation.
    """
    if len(targets) <= 2:
        return list(targets)

    remaining: list[tuple[WarehouseScanTarget, WarehouseLocalPose]] = [
        (target, _pose_from_json(target.scan_pose_local_json)) for target in targets
    ]
    first_target, first_pose = remaining.pop(0)
    ordered: list[tuple[WarehouseScanTarget, WarehouseLocalPose]] = [(first_target, first_pose)]

    while remaining:
        _, last_pose = ordered[-1]
        next_index = min(
            range(len(remaining)),
            key=lambda index: math.hypot(
                remaining[index][1].x_m - last_pose.x_m,
                remaining[index][1].y_m - last_pose.y_m,
            ),
        )
        ordered.append(remaining.pop(next_index))

    return [target for target, _pose in ordered]


def order_targets(
    targets: list[WarehouseScanTarget],
    *,
    optimize_order: bool,
) -> list[WarehouseScanTarget]:
    ordered = sorted(
        targets,
        key=lambda target: (
            _safe_int(getattr(target, "priority", 0), default=0),
            str(target.aisle_code or ""),
            str(target.rack_code or ""),
            _safe_int(getattr(target, "shelf_level", 0), default=0),
            str(target.bin_code or ""),
            _target_id(target),
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
    default_hover = (
        None
        if default_hover_time_s is None
        else _safe_float(default_hover_time_s, default=0.0, minimum=0.0)
    )
    default_timeout = (
        None
        if default_scan_timeout_s is None
        else _safe_float(default_scan_timeout_s, default=10.0, minimum=_MIN_TIMEOUT_S)
    )

    for target in targets:
        hover_time_s = default_hover if default_hover is not None else _target_hover_time_s(target)
        scan_timeout_s = (
            default_timeout if default_timeout is not None else _target_scan_timeout_s(target)
        )
        base_metadata = _metadata_for_target(target)

        from backend.modules.warehouse.service.inspection_planner import (
            semantic_target_waypoints,
        )

        waypoints.extend(
            semantic_target_waypoints(
                target,
                hover_time_s=hover_time_s,
                scan_timeout_s=scan_timeout_s,
                metadata=base_metadata,
            )
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
            extra={"target_id": _target_id(target), "barcode": target.barcode},
        )
        return ScanResult(
            status="success" if target.barcode else "failed",
            detected_barcode=target.barcode,
            confidence=1.0 if target.barcode else 0.0,
            error_message=None if target.barcode else "Mock scanner has no expected barcode.",
        )


async def _flush_mission_failed(db: AsyncSession, mission: WarehouseInspectionMission) -> None:
    try:
        mission.status = "failed"
        await db.flush()
    except Exception:
        logger.exception(
            "warehouse_inspection_mission_failed_status_flush_failed",
            extra={"mission_id": _safe_int(getattr(mission, "id", 0), default=0)},
        )


async def execute_inspection_mission(
    *,
    db: AsyncSession,
    mission: WarehouseInspectionMission,
    targets: list[WarehouseScanTarget],
    navigator: LocalNavigationAdapter,
    scanner: WarehouseScanner | None = None,
    speed_mps: float | None = None,
    runtime_gate: Callable[[], Awaitable[str | None]] | None = None,
    localization_method: str | None = None,
    replanner: Callable[[WarehouseScanTarget, int], Awaitable[LocalPose | None]] | None = None,
) -> None:
    from backend.modules.warehouse.service.inspection_execution_gate import localization_runtime_gate
    from backend.modules.warehouse.service.inspection_execution_policy import (
        InspectionExecutionPolicy,
        execution_action,
    )

    policy = InspectionExecutionPolicy(**dict(mission.runtime_policy_json or {}))
    if mission.approval_status != "approved":
        raise RuntimeError("Inspection mission preview is not approved")
    checksum = hashlib.sha256(
        json.dumps(
            mission.plan_json or {}, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    if not mission.plan_checksum or checksum != mission.plan_checksum:
        raise RuntimeError("Inspection mission plan changed after approval")
    from backend.modules.warehouse.service.mission_revisions import verify_mission_revision_pins

    await verify_mission_revision_pins(db, mission)
    frame_id = getattr(mission, "coordinate_frame_id", None)
    if frame_id is None:
        raise RuntimeError("Inspection mission has no locked coordinate-frame revision")
    mismatched = [
        _target_id(target)
        for target in targets
        if getattr(target, "coordinate_frame_id", None) != frame_id
    ]
    if mismatched:
        raise RuntimeError(f"Inspection targets use a different coordinate revision: {mismatched}")
    layout_id = getattr(mission, "layout_version_id", None)
    if layout_id is None:
        raise RuntimeError("Inspection mission has no locked layout revision")
    wrong_layout = [
        _target_id(target)
        for target in targets
        if getattr(target, "layout_version_id", None) != layout_id
    ]
    if wrong_layout:
        raise RuntimeError(f"Inspection targets use a different layout revision: {wrong_layout}")
    scanner = scanner or MockWarehouseScanner()
    mission_id = _safe_int(getattr(mission, "id", 0), default=0)
    mission.status = "running"
    await db.flush()
    logger.info("warehouse_inspection_mission_started", extra={"mission_id": mission_id})

    async def _runtime_gate() -> str | None:
        reason = await localization_runtime_gate(localization_method)
        if reason:
            return reason
        if runtime_gate is None:
            return None
        return await runtime_gate()

    critical_failure = False
    try:
        for target in targets:
            target_id = _target_id(target)
            pose_schema: WarehouseLocalPose | None = None
            try:
                reason = await _runtime_gate()
                if reason:
                    action = execution_action(reason=reason, replan_attempts=0, policy=policy)
                    if action == "abort_land":
                        mission.status = "aborted"
                        await navigator.safe_land()
                        await db.flush()
                        return
                    if action == "return_to_dock":
                        mission.status = "aborted"
                        await navigator.land_on_dock(None)
                        await db.flush()
                        return
                pose_schema = _pose_from_json(target.scan_pose_local_json)
                pose = _local_pose_from_schema(pose_schema)
                scan_timeout_s = _target_scan_timeout_s(target)
                hover_time_s = _target_hover_time_s(target)

                logger.info(
                    "warehouse_inspection_target_navigation_started",
                    extra={"mission_id": mission_id, "target_id": target_id},
                )
                attempts = 0
                while True:
                    try:
                        await navigator.goto_local_pose(
                            pose,
                            speed_mps=speed_mps,
                            timeout_s=max(10.0, scan_timeout_s),
                        )
                        break
                    except Exception:
                        action = execution_action(
                            reason="path_blocked", replan_attempts=attempts, policy=policy
                        )
                        if action != "replan" or replanner is None:
                            raise
                        attempts += 1
                        replacement = await replanner(target, attempts)
                        if replacement is None:
                            raise RuntimeError("Inspection replanner found no safe path") from None
                        pose = replacement
                logger.info(
                    "warehouse_inspection_target_reached",
                    extra={"mission_id": mission_id, "target_id": target_id},
                )

                await asyncio.wait_for(
                    navigator.hold_position(timeout_s=hover_time_s),
                    timeout=max(_MIN_TIMEOUT_S, hover_time_s + 1.0),
                )
                logger.info(
                    "warehouse_inspection_scan_started",
                    extra={"mission_id": mission_id, "target_id": target_id},
                )
                scan = await asyncio.wait_for(
                    scanner.scan_target(target, timeout_s=scan_timeout_s),
                    timeout=scan_timeout_s,
                )
            except TimeoutError as exc:
                logger.warning(
                    "warehouse_inspection_target_timeout",
                    extra={"mission_id": mission_id, "target_id": target_id},
                )
                scan = ScanResult(status="timeout", error_message=str(exc))
            except asyncio.CancelledError:
                logger.warning(
                    "warehouse_inspection_mission_cancelled",
                    extra={"mission_id": mission_id, "target_id": target_id},
                )
                await _flush_mission_failed(db, mission)
                raise
            except Exception as exc:
                logger.exception(
                    "warehouse_inspection_target_failed",
                    extra={"mission_id": mission_id, "target_id": target_id},
                )
                scan = ScanResult(status="failed", error_message=str(exc))

            pose_json = pose_schema.model_dump() if pose_schema is not None else None
            result = WarehouseInspectionResult(
                mission_id=mission_id,
                target_id=target_id,
                status=scan.status,
                expected_barcode=target.barcode,
                detected_barcode=scan.detected_barcode,
                confidence=scan.confidence,
                image_asset_id=scan.image_asset_id,
                video_asset_id=scan.video_asset_id,
                drone_pose_local_json=pose_json,
                error_message=scan.error_message,
                scanned_at=datetime.now(UTC),
            )
            db.add(result)
            await db.flush()
            logger.info(
                "warehouse_inspection_scan_result",
                extra={
                    "mission_id": mission_id,
                    "target_id": target_id,
                    "status": scan.status,
                },
            )

        if bool(mission.return_to_dock):
            try:
                await navigator.land_on_dock(None)
            except asyncio.CancelledError:
                await _flush_mission_failed(db, mission)
                raise
            except Exception:
                critical_failure = True
                logger.exception(
                    "warehouse_inspection_return_to_dock_failed",
                    extra={"mission_id": mission_id},
                )

        mission.status = "failed" if critical_failure else "completed"
        await db.flush()
        logger.info(
            "warehouse_inspection_mission_completed",
            extra={"mission_id": mission_id, "status": mission.status},
        )
        if mission.status == "completed":
            try:
                from backend.modules.agents.hooks import schedule_warehouse_inspection_postflight

                schedule_warehouse_inspection_postflight(inspection_mission_id=int(mission_id))
            except Exception:
                logger.exception("Failed to schedule warehouse inspection agent postflight")
    except Exception:
        if getattr(mission, "status", None) == "running":
            await _flush_mission_failed(db, mission)
        raise
