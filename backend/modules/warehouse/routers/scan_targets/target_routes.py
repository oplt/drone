"""Warehouse scan-target routes — CRUD and pose compute."""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_helpers import scan_target_out
from backend.modules.warehouse.models import WarehouseScanTarget
from backend.modules.warehouse.schemas import (
    WarehouseScanPoseComputeIn,
    WarehouseScanPoseComputeOut,
    WarehouseScanTargetCreate,
    WarehouseScanTargetRead,
    WarehouseScanTargetUpdate,
)

from backend.modules.warehouse.routers import scan_targets as scan_targets_api

from .helpers import _set_scan_target_cache_headers
from .router import router

logger = logging.getLogger(__name__)


@router.get("/maps/{warehouse_map_id}/scan-targets", response_model=Page[WarehouseScanTargetRead])
async def list_warehouse_scan_targets(
    warehouse_map_id: int,
    response: Response,
    active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> Page[WarehouseScanTargetRead]:
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    _set_scan_target_cache_headers(response, offset=page_offset)
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    clauses = [WarehouseScanTarget.warehouse_map_id == warehouse_map_id]
    if active is not None:
        clauses.append(WarehouseScanTarget.active.is_(active))
    total = int(
        (
            await db.execute(select(func.count()).select_from(WarehouseScanTarget).where(*clauses))
        ).scalar_one()
        or 0
    )
    rows = (
        (
            await db.execute(
                select(WarehouseScanTarget)
                .where(*clauses)
                .order_by(
                    WarehouseScanTarget.priority.asc(),
                    WarehouseScanTarget.aisle_code.asc(),
                    WarehouseScanTarget.rack_code.asc(),
                    WarehouseScanTarget.bin_code.asc(),
                    WarehouseScanTarget.id.asc(),
                )
                .limit(page_limit + 1)
                .offset(page_offset)
            )
        )
        .scalars()
        .all()
    )
    return page_from_offset(
        [scan_target_out(row) for row in rows],
        limit=page_limit,
        offset=page_offset,
        total=total,
    )


@router.post(
    "/maps/{warehouse_map_id}/scan-targets",
    response_model=WarehouseScanTargetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse_scan_target(
    warehouse_map_id: int,
    payload: WarehouseScanTargetCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseScanTargetRead:
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    frame = await scan_targets_api.get_locked_coordinate_frame(db, warehouse_map_id)
    if payload.coordinate_frame_id is not None and payload.coordinate_frame_id != int(frame.id):
        raise HTTPException(
            status_code=409,
            detail="Displayed coordinate revision is stale; reload the warehouse map",
        )
    scan_targets_api.require_warehouse_map_frames(
        [payload.target_point_local_json.model_dump(), payload.scan_pose_local_json.model_dump()]
    )
    location = await scan_targets_api.resolve_bin_context(
        db,
        warehouse_map_id=warehouse_map_id,
        bin_id=payload.bin_id,
        aisle_code=payload.aisle_code,
        rack_code=payload.rack_code,
        shelf_level=payload.shelf_level,
        bin_code=payload.bin_code,
    )
    if location.coordinate_frame_id != int(frame.id):
        raise HTTPException(409, "Locked layout uses a different coordinate revision")
    row = WarehouseScanTarget(
        warehouse_map_id=warehouse_map_id,
        reference_model_id=payload.reference_model_id,
        dock_station_id=payload.dock_station_id,
        layout_version_id=location.layout_version_id,
        bin_id=location.bin_id,
        aisle_code=location.aisle_code,
        rack_code=location.rack_code,
        shelf_level=location.shelf_level,
        bin_code=location.bin_code,
        sku=payload.sku,
        barcode=payload.barcode,
        product_name=payload.product_name,
        target_point_local_json=payload.target_point_local_json.model_dump(),
        coordinate_frame_id=int(frame.id),
        scan_pose_local_json=payload.scan_pose_local_json.model_dump(),
        sensor_aim_json=(
            payload.sensor_aim_json.model_dump() if payload.sensor_aim_json is not None else None
        ),
        shelf_normal_local_json=(
            payload.shelf_normal_local_json.model_dump()
            if payload.shelf_normal_local_json is not None
            else None
        ),
        scanner_metadata_json=dict(payload.scanner_metadata_json or {}),
        path_validation_json=dict(payload.path_validation_json or {}),
        failure_reason=payload.failure_reason,
        standoff_m=float(payload.standoff_m),
        hover_time_s=float(payload.hover_time_s),
        scan_timeout_s=float(payload.scan_timeout_s),
        priority=int(payload.priority),
        active=bool(payload.active),
    )
    try:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "warehouse_scan_target_created",
        extra={"warehouse_map_id": warehouse_map_id, "target_id": int(row.id)},
    )
    return scan_target_out(row)


@router.get(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    response_model=WarehouseScanTargetRead,
)
async def get_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScanTargetRead:
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await scan_targets_api.get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    return scan_target_out(row)


@router.patch(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    response_model=WarehouseScanTargetRead,
)
async def update_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    payload: WarehouseScanTargetUpdate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> WarehouseScanTargetRead:
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await scan_targets_api.get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    fields_set = getattr(payload, "model_fields_set", set())
    location_fields = {"bin_id", "aisle_code", "rack_code", "shelf_level", "bin_code"}
    if fields_set & location_fields:
        location = await scan_targets_api.resolve_bin_context(
            db,
            warehouse_map_id=warehouse_map_id,
            bin_id=payload.bin_id if "bin_id" in fields_set else row.bin_id,
            aisle_code=(
                payload.aisle_code
                if "aisle_code" in fields_set and payload.aisle_code is not None
                else row.aisle_code
            ),
            rack_code=payload.rack_code if "rack_code" in fields_set else row.rack_code,
            shelf_level=(payload.shelf_level if "shelf_level" in fields_set else row.shelf_level),
            bin_code=payload.bin_code if "bin_code" in fields_set else row.bin_code,
        )
        row.layout_version_id = location.layout_version_id
        row.bin_id = location.bin_id
        row.aisle_code = location.aisle_code
        row.rack_code = location.rack_code
        row.shelf_level = location.shelf_level
        row.bin_code = location.bin_code
    for field_name in (
        "reference_model_id",
        "dock_station_id",
        "sku",
        "barcode",
        "product_name",
        "standoff_m",
        "hover_time_s",
        "scan_timeout_s",
        "priority",
        "active",
        "failure_reason",
    ):
        if field_name in fields_set:
            setattr(row, field_name, getattr(payload, field_name))
    if "target_point_local_json" in fields_set and payload.target_point_local_json is not None:
        row.target_point_local_json = payload.target_point_local_json.model_dump()
    if "scan_pose_local_json" in fields_set and payload.scan_pose_local_json is not None:
        row.scan_pose_local_json = payload.scan_pose_local_json.model_dump()
    if "sensor_aim_json" in fields_set:
        row.sensor_aim_json = (
            payload.sensor_aim_json.model_dump() if payload.sensor_aim_json is not None else None
        )
    if "shelf_normal_local_json" in fields_set:
        row.shelf_normal_local_json = (
            payload.shelf_normal_local_json.model_dump()
            if payload.shelf_normal_local_json is not None
            else None
        )
    if "scanner_metadata_json" in fields_set:
        row.scanner_metadata_json = dict(payload.scanner_metadata_json or {})
    if "path_validation_json" in fields_set:
        row.path_validation_json = dict(payload.path_validation_json or {})
    validated = WarehouseScanTargetCreate.model_validate(
        {
            "reference_model_id": row.reference_model_id,
            "dock_station_id": row.dock_station_id,
            "aisle_code": row.aisle_code,
            "rack_code": row.rack_code,
            "shelf_level": row.shelf_level,
            "bin_code": row.bin_code,
            "sku": row.sku,
            "barcode": row.barcode,
            "product_name": row.product_name,
            "target_point_local_json": row.target_point_local_json,
            "scan_pose_local_json": row.scan_pose_local_json,
            "sensor_aim_json": row.sensor_aim_json,
            "shelf_normal_local_json": row.shelf_normal_local_json,
            "scanner_metadata_json": row.scanner_metadata_json,
            "path_validation_json": row.path_validation_json,
            "failure_reason": row.failure_reason,
            "standoff_m": row.standoff_m,
            "hover_time_s": row.hover_time_s,
            "scan_timeout_s": row.scan_timeout_s,
            "priority": row.priority,
            "active": row.active,
        }
    )
    row.target_point_local_json = validated.target_point_local_json.model_dump()
    row.scan_pose_local_json = validated.scan_pose_local_json.model_dump()
    row.sensor_aim_json = (
        validated.sensor_aim_json.model_dump() if validated.sensor_aim_json is not None else None
    )
    row.shelf_normal_local_json = (
        validated.shelf_normal_local_json.model_dump()
        if validated.shelf_normal_local_json is not None
        else None
    )
    row.scanner_metadata_json = dict(validated.scanner_metadata_json or {})
    row.path_validation_json = dict(validated.path_validation_json or {})
    row.failure_reason = validated.failure_reason
    try:
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        raise
    return scan_target_out(row)


@router.delete(
    "/maps/{warehouse_map_id}/scan-targets/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_warehouse_scan_target(
    warehouse_map_id: int,
    target_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> None:
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await scan_targets_api.get_scan_target_or_404(
        db,
        warehouse_map_id=warehouse_map_id,
        target_id=target_id,
    )
    row.active = False
    await db.commit()


@router.post("/scan-targets/compute-scan-pose", response_model=WarehouseScanPoseComputeOut)
async def compute_warehouse_scan_pose(
    payload: WarehouseScanPoseComputeIn,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseScanPoseComputeOut:
    return WarehouseScanPoseComputeOut(
        scan_pose=scan_targets_api.compute_scan_pose(
            target_point=payload.target_point,
            shelf_normal=payload.shelf_normal,
            standoff_m=payload.standoff_m,
            yaw_deg=payload.yaw_deg,
        )
    )
