from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.models import WarehouseCoordinateFrame, WarehouseMap
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
    created_at: datetime
    locked_at: datetime | None
    superseded_at: datetime | None


class CoordinateFrameValidationOut(BaseModel):
    valid: bool
    validation_warnings: list[dict[str, str]] = Field(default_factory=list)
    checksum_sha256: str


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
    if payload.confidence < 0.5:
        warnings.append(
            {"code": "localization_confidence_low", "message": "Frame cannot be locked below 0.5"}
        )
    if not payload.covariance:
        warnings.append(
            {"code": "covariance_missing", "message": "Locking requires a finite 6x6 covariance"}
        )
    return CoordinateFrameValidationOut(
        valid=not warnings,
        validation_warnings=warnings,
        checksum_sha256=transform_checksum(payload.transform.model_dump()),
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


@router.get("/maps/{warehouse_map_id}/coordinate-frames", response_model=list[CoordinateFrameOut])
async def list_coordinate_frames(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows = (
        (
            await db.execute(
                select(WarehouseCoordinateFrame)
                .where(WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id)
                .order_by(WarehouseCoordinateFrame.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_out(row) for row in rows]


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
