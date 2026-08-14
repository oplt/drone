"""Warehouse scan-target routes — bulk import."""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_write
from backend.modules.warehouse.http_helpers import scan_target_out
from backend.modules.warehouse.models import WarehouseScanTarget
from backend.modules.warehouse.schemas import WarehouseScanTargetImport, WarehouseScanTargetRead
from backend.modules.warehouse.service.frame_imports import normalize_scan_target_import

from backend.modules.warehouse.routers import scan_targets as scan_targets_api

from .router import router

logger = logging.getLogger(__name__)


@router.post(
    "/maps/{warehouse_map_id}/scan-targets/import",
    response_model=list[WarehouseScanTargetRead],
    status_code=status.HTTP_201_CREATED,
)
async def import_warehouse_scan_targets(
    warehouse_map_id: int,
    payload: WarehouseScanTargetImport,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> list[WarehouseScanTargetRead]:
    await scan_targets_api.assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    frame = await scan_targets_api.get_locked_coordinate_frame(db, warehouse_map_id)
    if payload.coordinate_frame_id is not None and payload.coordinate_frame_id != int(frame.id):
        raise HTTPException(409, "Import coordinate revision is stale")
    bin_index = await scan_targets_api.load_locked_layout_bin_index(db, warehouse_map_id=warehouse_map_id)
    rows: list[WarehouseScanTarget] = []
    try:
        for raw_target in payload.targets:
            try:
                target = normalize_scan_target_import(
                    raw_target,
                    source_frame_id=payload.source_frame_id,
                    odom_to_warehouse_map_transform=frame.transform_json,
                )
            except ValueError as exc:
                raise HTTPException(422, f"Invalid scan target import: {exc}") from exc
            if target.coordinate_frame_id is not None and target.coordinate_frame_id != int(
                frame.id
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Imported target coordinate revision is stale",
                )
            location = scan_targets_api.resolve_bin_context_from_index(
                bin_index,
                bin_id=target.bin_id,
                aisle_code=target.aisle_code,
                rack_code=target.rack_code,
                shelf_level=target.shelf_level,
                bin_code=target.bin_code,
            )
            if location.coordinate_frame_id != int(frame.id):
                raise HTTPException(409, "Locked layout uses a different coordinate revision")
            row = WarehouseScanTarget(
                warehouse_map_id=warehouse_map_id,
                coordinate_frame_id=int(frame.id),
                layout_version_id=location.layout_version_id,
                bin_id=location.bin_id,
                reference_model_id=target.reference_model_id,
                dock_station_id=target.dock_station_id,
                aisle_code=location.aisle_code,
                rack_code=location.rack_code,
                shelf_level=location.shelf_level,
                bin_code=location.bin_code,
                sku=target.sku,
                barcode=target.barcode,
                product_name=target.product_name,
                target_point_local_json=target.target_point_local_json.model_dump(),
                scan_pose_local_json=target.scan_pose_local_json.model_dump(),
                sensor_aim_json=(
                    target.sensor_aim_json.model_dump()
                    if target.sensor_aim_json is not None
                    else None
                ),
                shelf_normal_local_json=(
                    target.shelf_normal_local_json.model_dump()
                    if target.shelf_normal_local_json is not None
                    else None
                ),
                scanner_metadata_json=dict(target.scanner_metadata_json or {}),
                path_validation_json=dict(target.path_validation_json or {}),
                failure_reason=target.failure_reason,
                standoff_m=float(target.standoff_m),
                hover_time_s=float(target.hover_time_s),
                scan_timeout_s=float(target.scan_timeout_s),
                priority=int(target.priority),
                active=bool(target.active),
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        row_ids = [int(row.id) for row in rows]
        persisted_rows = list(
            (
                await db.execute(
                    select(WarehouseScanTarget)
                    .where(WarehouseScanTarget.id.in_(row_ids))
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        persisted_by_id = {int(row.id): row for row in persisted_rows}
        if len(persisted_by_id) != len(row_ids):
            raise RuntimeError("Failed to reload all imported warehouse scan targets")
        rows = [persisted_by_id[row_id] for row_id in row_ids]
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info(
        "warehouse_scan_targets_imported",
        extra={"warehouse_map_id": warehouse_map_id, "count": len(rows)},
    )
    scan_targets_api.emit_coordinate_audit(
        event_name="warehouse_scan_targets_imported",
        action="transform_import" if payload.source_frame_id == "odom" else "import_layout",
        resource_type="warehouse_scan_target_batch",
        resource_id=f"map:{warehouse_map_id}:frame:{frame.id}",
        warehouse_map_id=warehouse_map_id,
        org_user=org_user,
        reason=f"operator_import_from_{payload.source_frame_id}",
        coordinate_frame_id=int(frame.id),
        coordinate_frame_version=int(frame.version),
        covariance=list(getattr(frame, "covariance_json", None) or []),
        transform_age_ms_value=scan_targets_api.transform_age_ms(getattr(frame, "locked_at", None)),
        validation_result="pass",
        extra={
            "source_frame_id": payload.source_frame_id,
            "target_frame_id": "warehouse_map",
            "target_count": len(rows),
            "transform_applied": payload.source_frame_id == "odom",
        },
    )
    return [scan_target_out(row) for row in rows]
