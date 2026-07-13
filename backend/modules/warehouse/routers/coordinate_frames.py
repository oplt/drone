from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.models import (
    WarehouseCoordinateFrame,
    WarehouseDockStation,
    WarehouseMap,
    WarehouseSensorRig,
)
from backend.modules.warehouse.service.coordinate_audit import emit_coordinate_audit
from backend.modules.warehouse.service.coordinate_diagnostics import build_coordinate_diagnostics
from backend.modules.warehouse.service.localization_tf_sync import sync_locked_coordinate_frame_to_ros
from backend.modules.warehouse.service.coordinate_frames import validate_transform
from backend.modules.warehouse.service.drift_guard import (
    ensure_no_active_missions_for_frame_change,
    transform_checksum,
    validate_localization_evidence,
)
from backend.modules.warehouse.service.frame_contract import frame_contract_payload

router = APIRouter(tags=["warehouse-coordinate-frames"])
logger = logging.getLogger(__name__)


class Translation3D(BaseModel):
    x: float
    y: float
    z: float


class UnitQuaternion(BaseModel):
    x: float
    y: float
    z: float
    w: float


class RigidTransform(BaseModel):
    translation: Translation3D
    rotation: UnitQuaternion


class CoordinateFrameCreate(BaseModel):
    transform: RigidTransform
    source: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(..., ge=0.0, le=1.0)
    covariance: list[float] = Field(default_factory=list, max_length=36)
    transform_timestamp: datetime
    max_age_s: float = Field(default=300.0, gt=0.0, le=86_400.0)
    localization_method: str = Field(..., min_length=1, max_length=64)
    commissioning_evidence: dict[str, Any] = Field(default_factory=dict)
    lock: bool = False

    @field_validator("transform")
    @classmethod
    def valid_transform(cls, value: RigidTransform) -> RigidTransform:
        validate_transform(value.model_dump())
        return value

    @field_validator("covariance")
    @classmethod
    def valid_covariance(cls, value: list[float]) -> list[float]:
        if value and len(value) != 36:
            raise ValueError("covariance must be empty or a row-major 6x6 matrix")
        return value

    @model_validator(mode="after")
    def valid_locked_evidence(self) -> CoordinateFrameCreate:
        if self.lock:
            validate_localization_evidence(
                transform=self.transform.model_dump(),
                transform_timestamp=self.transform_timestamp,
                max_age_s=self.max_age_s,
                covariance=self.covariance,
                confidence=self.confidence,
            )
        return self


class CoordinateFrameOut(BaseModel):
    id: int
    warehouse_map_id: int
    version: int
    parent_frame_id: str
    child_frame_id: str
    units: Literal["m"]
    axis_convention: Literal["ENU"]
    handedness: Literal["right"]
    transform: RigidTransform
    source: str
    status: Literal["draft", "locked", "superseded"]
    confidence: float | None
    covariance: list[float]
    transform_timestamp: datetime
    max_age_s: float
    localization_method: str
    transform_checksum: str
    meta_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    locked_at: datetime | None
    superseded_at: datetime | None


class CoordinateFrameValidationOut(BaseModel):
    valid: bool
    validation_warnings: list[dict[str, str]] = Field(default_factory=list)
    checksum_sha256: str
    commissioning_report: dict[str, Any] = Field(default_factory=dict)


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


def _out(row: WarehouseCoordinateFrame) -> CoordinateFrameOut:
    return CoordinateFrameOut(
        id=row.id,
        warehouse_map_id=row.warehouse_map_id,
        version=row.version,
        parent_frame_id=row.parent_frame_id,
        child_frame_id=row.child_frame_id,
        units=row.units,
        axis_convention=row.axis_convention,
        handedness=row.handedness,
        transform=row.transform_json,
        source=row.source,
        status=row.status,
        confidence=row.confidence,
        covariance=list(row.covariance_json or []),
        transform_timestamp=row.transform_timestamp,
        max_age_s=row.max_age_s,
        localization_method=row.localization_method,
        transform_checksum=row.transform_checksum,
        meta_data=dict(getattr(row, "meta_data", {}) or {}),
        created_at=row.created_at,
        locked_at=row.locked_at,
        superseded_at=row.superseded_at,
    )


@router.post(
    "/maps/{warehouse_map_id}/coordinate-frame/validate",
    response_model=CoordinateFrameValidationOut,
)
async def validate_coordinate_frame_payload(
    warehouse_map_id: int,
    payload: CoordinateFrameCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> CoordinateFrameValidationOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    warnings = []
    if payload.confidence < 0.7:
        warnings.append(
            {"code": "localization_confidence_low", "message": "Frame cannot be locked below 0.7"}
        )
    if not payload.covariance:
        warnings.append(
            {"code": "covariance_missing", "message": "Locking requires a finite 6x6 covariance"}
        )
    commissioning_report = await _commissioning_report(
        db,
        warehouse_map_id=warehouse_map_id,
        payload=payload,
    )
    warnings.extend(commissioning_report.get("issues") or [])
    return CoordinateFrameValidationOut(
        valid=not warnings,
        validation_warnings=warnings,
        checksum_sha256=transform_checksum(payload.transform.model_dump()),
        commissioning_report=commissioning_report,
    )


@router.post(
    "/maps/{warehouse_map_id}/coordinate-frames/{version}/lock",
    response_model=CoordinateFrameOut,
)
async def lock_coordinate_frame(
    warehouse_map_id: int,
    version: int,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> CoordinateFrameOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    expected = str(if_match or "").strip().removeprefix("W/").strip('"')
    if not expected:
        raise HTTPException(428, "If-Match is required")
    if expected != str(version):
        raise HTTPException(412, "Coordinate frame revision mismatch")
    await ensure_no_active_missions_for_frame_change(db, warehouse_map_id=warehouse_map_id)
    row = (
        await db.execute(
            select(WarehouseCoordinateFrame).where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.version == version,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Coordinate frame not found")
    if row.status != "draft":
        raise HTTPException(409, "Only draft coordinate frames can be locked")
    try:
        evidence = validate_localization_evidence(
            transform=row.transform_json,
            transform_timestamp=row.transform_timestamp,
            max_age_s=float(row.max_age_s),
            covariance=list(row.covariance_json or []),
            confidence=float(row.confidence or 0.0),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if evidence["checksum_sha256"] != row.transform_checksum:
        raise HTTPException(409, "Coordinate frame checksum mismatch")
    commissioning_report = await _require_commissioned_frame(
        db,
        warehouse_map_id=warehouse_map_id,
        row=row,
    )
    now = datetime.now(UTC)
    await db.execute(
        update(WarehouseCoordinateFrame)
        .where(
            WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
            WarehouseCoordinateFrame.status == "locked",
        )
        .values(status="superseded", superseded_at=now)
    )
    row.status = "locked"
    row.locked_at = now
    row.meta_data = {
        **dict(row.meta_data or {}),
        "commissioning_report": commissioning_report,
    }
    await db.commit()
    await db.refresh(row)
    synced, sync_detail = await sync_locked_coordinate_frame_to_ros(db, warehouse_map_id=warehouse_map_id)
    if not synced:
        logger.warning(
            "Locked coordinate frame v%s but ROS localization sync failed: %s",
            row.version,
            sync_detail,
        )
    return _out(row)


class CoordinateDiagnosticsOut(BaseModel):
    warehouse_map_id: int
    generated_at: str
    mission_ready: bool
    coordinate_frame: dict | None
    latest_coordinate_frame: dict | None
    layout_version: dict | None
    latest_layout_version: dict | None
    localization_evidence: dict | None
    entity_counts: dict[str, int]
    frame_contract_checksum: str | None
    ros_map_odom_tf: dict | None = None
    ros_tf_tree: dict | None = None
    slam_localization: dict | None = None
    provisional_epoch: dict | None = None
    blocking_issues: list[dict[str, str]]
    warnings: list[dict[str, str]]


@router.get("/maps/{warehouse_map_id}/coordinate-diagnostics", response_model=CoordinateDiagnosticsOut)
async def get_coordinate_diagnostics(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> CoordinateDiagnosticsOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    payload = await build_coordinate_diagnostics(db, warehouse_map_id=warehouse_map_id)
    return CoordinateDiagnosticsOut.model_validate(payload)


@router.post("/maps/{warehouse_map_id}/coordinate-frames/sync-ros")
async def sync_coordinate_frame_to_ros(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> dict[str, object]:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    synced, detail = await sync_locked_coordinate_frame_to_ros(db, warehouse_map_id=warehouse_map_id)
    if not synced:
        raise HTTPException(409, detail)
    return {"synced": True, "detail": detail}


@router.get("/maps/{warehouse_map_id}/frame-contract")
async def get_warehouse_frame_contract(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    active = (
        await db.execute(
            select(WarehouseCoordinateFrame).where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
        )
    ).scalar_one_or_none()
    return frame_contract_payload(coordinate_frame=active)


@router.get("/maps/{warehouse_map_id}/coordinate-frames", response_model=Page[CoordinateFrameOut])
async def list_coordinate_frames(
    warehouse_map_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = (
        (
            await db.execute(
                select(WarehouseCoordinateFrame)
                .where(WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id)
                .order_by(
                    WarehouseCoordinateFrame.version.desc(),
                    WarehouseCoordinateFrame.id.desc(),
                )
                .offset(page_offset)
                .limit(page_limit + 1)
            )
        )
        .scalars()
        .all()
    )
    return page_from_offset(
        [_out(row) for row in rows], limit=page_limit, offset=page_offset
    )


@router.get(
    "/maps/{warehouse_map_id}/coordinate-frames/active",
    response_model=CoordinateFrameOut,
)
async def get_active_coordinate_frame(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = (
        await db.execute(
            select(WarehouseCoordinateFrame).where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "No locked coordinate frame exists for this warehouse map")
    return _out(row)


@router.post(
    "/maps/{warehouse_map_id}/coordinate-frames",
    response_model=CoordinateFrameOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_coordinate_frame(
    payload: CoordinateFrameCreate,
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    await db.execute(
        select(WarehouseMap.id).where(WarehouseMap.id == warehouse_map_id).with_for_update()
    )
    if payload.lock and payload.confidence <= 0:
        raise HTTPException(422, "Locked localization requires positive confidence")
    if payload.lock:
        await ensure_no_active_missions_for_frame_change(db, warehouse_map_id=warehouse_map_id)
        commissioning_report = await _require_commissioned_frame(
            db,
            warehouse_map_id=warehouse_map_id,
            payload=payload,
        )
    else:
        commissioning_report = await _commissioning_report(
            db,
            warehouse_map_id=warehouse_map_id,
            payload=payload,
        )
    previous = (
        await db.execute(
            select(WarehouseCoordinateFrame).where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
        )
    ).scalar_one_or_none()
    version = (
        int(
            (
                await db.execute(
                    select(func.coalesce(func.max(WarehouseCoordinateFrame.version), 0)).where(
                        WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id
                    )
                )
            ).scalar_one()
        )
        + 1
    )
    try:
        if payload.lock:
            await db.execute(
                update(WarehouseCoordinateFrame)
                .where(
                    WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                    WarehouseCoordinateFrame.status == "locked",
                )
                .values(status="superseded", superseded_at=datetime.now(UTC))
            )
        row = WarehouseCoordinateFrame(
            warehouse_map_id=warehouse_map_id,
            version=version,
            parent_frame_id="warehouse_map",
            child_frame_id="odom",
            units="m",
            axis_convention="ENU",
            handedness="right",
            transform_json=payload.transform.model_dump(),
            covariance_json=payload.covariance,
            source=payload.source.strip(),
            localization_method=payload.localization_method.strip(),
            transform_timestamp=payload.transform_timestamp,
            max_age_s=payload.max_age_s,
            transform_checksum=transform_checksum(payload.transform.model_dump()),
            confidence=payload.confidence,
            meta_data={
                "commissioning_evidence": dict(payload.commissioning_evidence or {}),
                "commissioning_report": commissioning_report,
            },
            status="locked" if payload.lock else "draft",
            locked_at=datetime.now(UTC) if payload.lock else None,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    emit_coordinate_audit(
        event_name="warehouse_coordinate_frame_created",
        action="lock" if payload.lock else "create_draft",
        resource_type="warehouse_coordinate_frame",
        resource_id=row.id,
        warehouse_map_id=warehouse_map_id,
        org_user=org_user,
        reason=payload.source,
        coordinate_frame_id=row.id,
        coordinate_frame_version=row.version,
        old_value=previous.transform_json if previous is not None else None,
        new_value=row.transform_json,
        covariance=list(row.covariance_json or []),
        validation_result="pass",
        extra={"confidence": row.confidence, "status": row.status},
    )
    if payload.lock:
        synced, sync_detail = await sync_locked_coordinate_frame_to_ros(
            db, warehouse_map_id=warehouse_map_id
        )
        if not synced:
            logger.warning(
                "Locked coordinate frame v%s but ROS localization sync failed: %s",
                row.version,
                sync_detail,
            )
    return _out(row)
