from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseScanTarget,
)
from backend.modules.warehouse.schemas import WarehouseInspectionWaypoint, WarehouseLocalPose
from backend.modules.warehouse.service.inspection_planner import semantic_target_waypoints
from backend.modules.warehouse.service.scan_to_layout import CandidateInput, persist_candidates

LOW_CONFIDENCE_RESCAN_THRESHOLD = 0.75
LAYOUT_DRIFT_REPORT_ASSET_TYPE = "LAYOUT_DRIFT_REPORT"


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _target_identity(target: WarehouseScanTarget) -> str:
    return "/".join(
        str(value)
        for value in (
            target.aisle_code,
            target.rack_code or "",
            target.shelf_level if target.shelf_level is not None else "",
            target.bin_code or "",
        )
    )


def _point_xyz(payload: dict[str, Any] | None) -> tuple[float, float, float] | None:
    if not isinstance(payload, dict):
        return None
    x = _finite_float(payload.get("x_m", payload.get("x")))
    y = _finite_float(payload.get("y_m", payload.get("y")))
    z = _finite_float(payload.get("z_m", payload.get("z", 0.0)))
    if x is None or y is None or z is None:
        return None
    return x, y, z


def _unit_normal(payload: dict[str, Any] | None) -> tuple[float, float, float] | None:
    raw = _point_xyz(payload)
    if raw is None:
        return None
    length = math.sqrt(sum(value * value for value in raw))
    if length <= 1e-9:
        return None
    return tuple(value / length for value in raw)


def observed_target_point(
    target: WarehouseScanTarget,
    result: WarehouseInspectionResult,
) -> dict[str, Any] | None:
    pose = _point_xyz(result.drone_pose_local_json)
    normal = _unit_normal(target.shelf_normal_local_json)
    if pose is None or normal is None:
        return None
    standoff = _finite_float(target.standoff_m) or 0.0
    return {
        "frame_id": "warehouse_map",
        "x_m": pose[0] + normal[0] * standoff,
        "y_m": pose[1] + normal[1] * standoff,
        "z_m": pose[2] + normal[2] * standoff,
        "source": "inspection_observation",
    }


def _result_confidence(result: WarehouseInspectionResult) -> float:
    confidence = _finite_float(result.confidence)
    if confidence is None:
        confidence = 0.0 if result.status in {"failed", "timeout"} else 0.5
    if result.status == "mismatch":
        confidence = min(confidence, 0.45)
    if result.status in {"failed", "timeout", "skipped"}:
        confidence = min(confidence, 0.25)
    return max(0.0, min(1.0, confidence))


def should_rescan(result: WarehouseInspectionResult) -> tuple[bool, str]:
    confidence = _result_confidence(result)
    if result.status in {"failed", "timeout", "mismatch"}:
        return True, f"scan_status_{result.status}"
    if confidence < LOW_CONFIDENCE_RESCAN_THRESHOLD:
        return True, "low_confidence"
    return False, ""


def rescan_waypoints_for_result(
    target: WarehouseScanTarget,
    result: WarehouseInspectionResult,
) -> list[WarehouseInspectionWaypoint]:
    needed, reason = should_rescan(result)
    if not needed:
        return []
    return semantic_target_waypoints(
        target,
        hover_time_s=float(target.hover_time_s),
        scan_timeout_s=float(target.scan_timeout_s),
        metadata={
            "rescan": True,
            "rescan_reason": reason,
            "inspection_result_id": int(result.id) if result.id is not None else None,
            "confidence": _result_confidence(result),
        },
        include_mission_legs=False,
    )


async def persist_inspection_feedback(
    db: AsyncSession,
    *,
    mission: WarehouseInspectionMission,
    target: WarehouseScanTarget,
    result: WarehouseInspectionResult,
) -> list[Any]:
    observed = observed_target_point(target, result)
    if observed is None:
        return []
    identity = _target_identity(target)
    geometry = {
        "target_point": observed,
        "expected_target_point": target.target_point_local_json,
        "expected_barcode": result.expected_barcode,
        "detected_barcode": result.detected_barcode,
        "status": result.status,
        "image_asset_id": result.image_asset_id,
        "video_asset_id": result.video_asset_id,
        "mission_id": int(mission.id),
        "inspection_result_id": int(result.id),
    }
    return await persist_candidates(
        db,
        warehouse_map_id=int(mission.warehouse_map_id),
        layout_version_id=mission.layout_version_id,
        confirmed_geometry={identity: {"target_point": target.target_point_local_json}},
        candidates=[
            CandidateInput(
                entity_kind="inspection_target",
                identity_key=identity,
                geometry=geometry,
                confidence=_result_confidence(result),
                source_sequence=int(result.id),
            )
        ],
    )


def append_rescan_plan(
    mission: WarehouseInspectionMission,
    *,
    target: WarehouseScanTarget,
    result: WarehouseInspectionResult,
) -> None:
    waypoints = rescan_waypoints_for_result(target, result)
    if not waypoints:
        return
    plan = dict(mission.plan_json or {})
    existing = list(plan.get("rescan_waypoints") or [])
    existing.extend(waypoint.model_dump() for waypoint in waypoints)
    plan["rescan_waypoints"] = existing
    summary = dict(plan.get("rescan_summary") or {})
    summary["count"] = len(existing)
    summary["updated_at"] = datetime.now(UTC).isoformat()
    plan["rescan_summary"] = summary
    mission.plan_json = plan


async def build_layout_drift_report(
    db: AsyncSession,
    *,
    mission: WarehouseInspectionMission,
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(WarehouseInspectionResult, WarehouseScanTarget)
            .join(WarehouseScanTarget, WarehouseScanTarget.id == WarehouseInspectionResult.target_id)
            .where(WarehouseInspectionResult.mission_id == int(mission.id))
        )
    ).all()
    samples: list[dict[str, Any]] = []
    for result, target in rows:
        observed = observed_target_point(target, result)
        expected = _point_xyz(target.target_point_local_json)
        actual = _point_xyz(observed)
        if expected is None or actual is None:
            continue
        displacement = math.dist(expected, actual)
        samples.append(
            {
                "target_id": int(target.id),
                "identity_key": _target_identity(target),
                "status": result.status,
                "confidence": _result_confidence(result),
                "displacement_m": round(displacement, 4),
                "expected_barcode": result.expected_barcode,
                "detected_barcode": result.detected_barcode,
            }
        )
    displacements = [float(item["displacement_m"]) for item in samples]
    report = {
        "mission_id": int(mission.id),
        "warehouse_map_id": int(mission.warehouse_map_id),
        "layout_version_id": mission.layout_version_id,
        "coordinate_frame_id": mission.coordinate_frame_id,
        "sample_count": len(samples),
        "max_displacement_m": max(displacements) if displacements else None,
        "mean_displacement_m": (
            sum(displacements) / len(displacements) if displacements else None
        ),
        "low_confidence_count": sum(
            1 for item in samples if float(item["confidence"]) < LOW_CONFIDENCE_RESCAN_THRESHOLD
        ),
        "mismatch_count": sum(1 for item in samples if item["status"] == "mismatch"),
        "samples": samples,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    previous = (
        await db.execute(
            select(WarehouseInspectionMission)
            .where(
                WarehouseInspectionMission.warehouse_map_id == int(mission.warehouse_map_id),
                WarehouseInspectionMission.status == "completed",
                WarehouseInspectionMission.id != int(mission.id),
            )
            .order_by(WarehouseInspectionMission.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if previous is not None:
        report["previous_completed_mission_id"] = int(previous.id)
    return report


async def persist_layout_drift_report(
    db: AsyncSession,
    *,
    mission: WarehouseInspectionMission,
) -> dict[str, Any]:
    report = await build_layout_drift_report(db, mission=mission)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    checksum = hashlib.sha256(encoded.encode()).hexdigest()
    if mission.map_model_id is not None:
        db.add(
            WarehouseAsset(
                model_id=int(mission.map_model_id),
                coordinate_frame_id=mission.coordinate_frame_id,
                frame_id="warehouse_map",
                type=LAYOUT_DRIFT_REPORT_ASSET_TYPE,
                url=f"memory://warehouse-layout-drift/{int(mission.id)}",
                checksum=checksum,
                meta_data=report,
            )
        )
    return report
