"""Warehouse coordinate-frame routes — create and lock."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_write
from backend.modules.warehouse.models import WarehouseCoordinateFrame, WarehouseMap

from .commissioning import _commissioning_report, _require_commissioned_frame
from .deps import (
    emit_coordinate_audit,
    ensure_no_active_missions_for_frame_change,
    get_map_or_404,
    sync_locked_coordinate_frame_to_ros,
    transform_checksum,
    validate_localization_evidence,
)
from .helpers import _out
from .router import router
from .schemas import CoordinateFrameCreate, CoordinateFrameOut

logger = logging.getLogger(__name__)


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
