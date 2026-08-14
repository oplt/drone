"""Warehouse coordinate-frame routes — commissioning validation."""

from __future__ import annotations

import math
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseCoordinateFrame,
    WarehouseDockStation,
    WarehouseSensorRig,
)

from .schemas import CoordinateFrameCreate

_LOCALIZATION_CHECK_KINDS = {"slam", "vslam", "lidar_slam", "scan_alignment"}
_ANCHOR_CHECK_KINDS = {"landmark", "survey", "dock_marker", "apriltag", "aruco"}


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _is_identity_transform(transform: dict[str, Any]) -> bool:
    translation = transform.get("translation") if isinstance(transform, dict) else {}
    rotation = transform.get("rotation") if isinstance(transform, dict) else {}
    try:
        tx, ty, tz = (float(translation.get(axis) or 0.0) for axis in ("x", "y", "z"))
        qx, qy, qz = (float(rotation.get(axis) or 0.0) for axis in ("x", "y", "z"))
        qw = float(rotation.get("w") or 1.0)
    except (TypeError, ValueError):
        return False
    return (
        math.dist((tx, ty, tz), (0.0, 0.0, 0.0)) <= 1e-9
        and math.dist((qx, qy, qz, qw), (0.0, 0.0, 0.0, 1.0)) <= 1e-9
    )


def _covariance_placeholder(covariance: list[float]) -> bool:
    if len(covariance) != 36:
        return True
    try:
        values = [float(value) for value in covariance]
    except (TypeError, ValueError):
        return True
    if not all(math.isfinite(value) for value in values):
        return True
    diagonal = [values[index] for index in (0, 7, 14)]
    return all(abs(value) <= 1e-12 for value in diagonal)


def _clean_checks(raw: Any) -> list[dict[str, Any]]:
    checks = raw if isinstance(raw, list) else []
    cleaned: list[dict[str, Any]] = []
    for item in checks:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if not kind:
            continue
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        residual_m = item.get("residual_m")
        yaw_residual_deg = item.get("yaw_residual_deg")
        cleaned.append(
            {
                "kind": kind,
                "passed": bool(item.get("passed", True)),
                "confidence": max(0.0, min(1.0, confidence)) if math.isfinite(confidence) else 0.0,
                "residual_m": (
                    float(residual_m)
                    if isinstance(residual_m, (int, float)) and math.isfinite(float(residual_m))
                    else None
                ),
                "yaw_residual_deg": (
                    float(yaw_residual_deg)
                    if isinstance(yaw_residual_deg, (int, float))
                    and math.isfinite(float(yaw_residual_deg))
                    else None
                ),
            }
        )
    return cleaned


def _residual_metrics(checks: list[dict[str, Any]], covariance: list[float]) -> dict[str, Any]:
    residuals = [
        float(check["residual_m"])
        for check in checks
        if isinstance(check.get("residual_m"), (int, float))
    ]
    yaw_residuals = [
        abs(float(check["yaw_residual_deg"]))
        for check in checks
        if isinstance(check.get("yaw_residual_deg"), (int, float))
    ]
    cov_values = [float(value) for value in covariance] if len(covariance) == 36 else []
    position_std_m = (
        math.sqrt(max(float(cov_values[index]) for index in (0, 7, 14)))
        if cov_values
        else None
    )
    return {
        "translation_residual_count": len(residuals),
        "translation_residual_mean_m": (
            round(sum(residuals) / len(residuals), 4) if residuals else None
        ),
        "translation_residual_max_m": round(max(residuals), 4) if residuals else None,
        "yaw_residual_max_deg": round(max(yaw_residuals), 3) if yaw_residuals else None,
        "position_std_m": round(position_std_m, 4) if position_std_m is not None else None,
    }


async def _commissioning_report(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    payload: CoordinateFrameCreate | None = None,
    row: WarehouseCoordinateFrame | None = None,
) -> dict[str, Any]:
    transform = payload.transform.model_dump() if payload is not None else row.transform_json
    covariance = list(payload.covariance if payload is not None else row.covariance_json or [])
    confidence = float(payload.confidence if payload is not None else row.confidence or 0.0)
    localization_method = str(
        payload.localization_method if payload is not None else row.localization_method or ""
    )
    evidence = (
        dict(payload.commissioning_evidence or {})
        if payload is not None
        else dict((row.meta_data or {}).get("commissioning_evidence") or {})
    )
    checks = _clean_checks(evidence.get("localization_checks"))
    active_docks = int(
        (
            await db.execute(
                select(func.count())
                .select_from(WarehouseDockStation)
                .where(
                    WarehouseDockStation.warehouse_map_id == int(warehouse_map_id),
                    WarehouseDockStation.active.is_(True),
                )
            )
        ).scalar_one()
        or 0
    )
    active_calibrated_rigs = int(
        (
            await db.execute(
                select(func.count())
                .select_from(WarehouseSensorRig)
                .where(
                    WarehouseSensorRig.active.is_(True),
                    WarehouseSensorRig.calibration_status == "valid",
                    WarehouseSensorRig.calibration_hash.is_not(None),
                )
            )
        ).scalar_one()
        or 0
    )
    passed_kinds = {
        str(check["kind"])
        for check in checks
        if bool(check.get("passed")) and float(check.get("confidence") or 0.0) >= 0.7
    }
    issues: list[dict[str, str]] = []
    if active_docks <= 0 and not bool(evidence.get("dock_pose_confirmed")):
        issues.append(_issue("dock_pose_missing", "Commissioning requires a dock pose."))
    sensor_hash = str(evidence.get("sensor_calibration_hash") or "").strip()
    if not sensor_hash and active_calibrated_rigs <= 0:
        issues.append(
            _issue("sensor_calibration_missing", "Commissioning requires sensor calibration hash.")
        )
    if _covariance_placeholder(covariance):
        issues.append(_issue("covariance_placeholder", "Locking requires non-placeholder covariance."))
    if confidence < 0.7:
        issues.append(_issue("localization_confidence_low", "Locking requires confidence >= 0.7."))
    if not (passed_kinds & _LOCALIZATION_CHECK_KINDS):
        issues.append(_issue("slam_check_missing", "Require a SLAM/scan localization check."))
    if not (passed_kinds & _ANCHOR_CHECK_KINDS):
        issues.append(
            _issue("landmark_check_missing", "Require an independent landmark/survey check.")
        )
    if len(passed_kinds) < 2:
        issues.append(
            _issue("independent_checks_missing", "Require at least 2 independent localization checks.")
        )
    if _is_identity_transform(transform) and not (
        bool(evidence.get("explicit_simulation_identity"))
        or localization_method.lower() in {"simulation", "sim", "gazebo"}
    ):
        issues.append(
            _issue(
                "identity_transform_not_allowed",
                "Identity transform requires explicit simulation evidence.",
            )
        )
    metrics = _residual_metrics(checks, covariance)
    return {
        "passed": not issues,
        "issues": issues,
        "check_kinds": sorted(passed_kinds),
        "active_dock_count": active_docks,
        "active_calibrated_sensor_rig_count": active_calibrated_rigs,
        "residual_metrics": metrics,
        "commissioning_evidence": {
            "dock_pose_confirmed": bool(evidence.get("dock_pose_confirmed")),
            "sensor_calibration_hash": sensor_hash or None,
            "localization_checks": checks,
            "explicit_simulation_identity": bool(evidence.get("explicit_simulation_identity")),
        },
    }


async def _require_commissioned_frame(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    payload: CoordinateFrameCreate | None = None,
    row: WarehouseCoordinateFrame | None = None,
) -> dict[str, Any]:
    report = await _commissioning_report(
        db,
        warehouse_map_id=warehouse_map_id,
        payload=payload,
        row=row,
    )
    if report["issues"]:
        raise HTTPException(422, {"code": "commissioning_incomplete", "report": report})
    return report


__all__ = ["_commissioning_report", "_require_commissioned_frame"]
