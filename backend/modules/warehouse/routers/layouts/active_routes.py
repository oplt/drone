"""Warehouse layout routes — active layout read and confirm."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import assert_map_or_404
from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseSafetyZone,
    WarehouseScanTarget,
    WarehouseShelf,
)
from backend.modules.warehouse.service.coordinate_audit import emit_coordinate_audit

from .router import router
from .schemas import WarehouseLayoutBinOut, WarehouseLayoutOut, WarehouseSafetyZoneOut


@router.get("/maps/{warehouse_map_id}/layouts/active", response_model=WarehouseLayoutOut)
async def get_active_warehouse_layout(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLayoutOut:
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = (
        await db.execute(
            select(WarehouseLayoutVersion).where(
                WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id,
                WarehouseLayoutVersion.status == "locked",
            )
        )
    ).scalar_one_or_none()
    if layout is None:
        raise HTTPException(404, "No locked warehouse layout exists")
    rows = (
        await db.execute(
            select(WarehouseAisle, WarehouseRack, WarehouseShelf, WarehouseBin)
            .join(WarehouseRack, WarehouseRack.aisle_id == WarehouseAisle.id)
            .join(WarehouseShelf, WarehouseShelf.rack_id == WarehouseRack.id)
            .join(WarehouseBin, WarehouseBin.shelf_id == WarehouseShelf.id)
            .where(WarehouseAisle.layout_version_id == layout.id)
            .order_by(
                WarehouseAisle.code,
                WarehouseRack.code,
                WarehouseShelf.level,
                WarehouseBin.code,
            )
        )
    ).all()
    zones = (
        (
            await db.execute(
                select(WarehouseSafetyZone).where(
                    WarehouseSafetyZone.layout_version_id == layout.id
                )
            )
        )
        .scalars()
        .all()
    )
    return WarehouseLayoutOut(
        id=layout.id,
        warehouse_map_id=layout.warehouse_map_id,
        coordinate_frame_id=layout.coordinate_frame_id,
        version=layout.version,
        revision=layout.revision,
        status=layout.status,
        source=layout.source,
        provenance_status=layout.provenance_status,
        artifact_set_id=layout.artifact_set_id,
        input_checksum=layout.input_checksum,
        algorithm_version=layout.algorithm_version,
        created_at=layout.created_at,
        locked_at=layout.locked_at,
        bins=[
            WarehouseLayoutBinOut(
                id=bin_row.id,
                aisle_code=aisle.code,
                rack_code=rack.code,
                shelf_level=shelf.level,
                bin_code=bin_row.code,
                geometry=bin_row.geometry_json or {},
            )
            for aisle, rack, shelf, bin_row in rows
        ],
        safety_zones=[
            WarehouseSafetyZoneOut(
                id=zone.id,
                code=zone.code,
                kind=zone.kind,
                geometry=zone.geometry_json or {},
                min_z_m=zone.min_z_m,
                max_z_m=zone.max_z_m,
                active=zone.active,
            )
            for zone in zones
        ],
    )


@router.post("/maps/{warehouse_map_id}/layouts/{layout_id}/confirm")
async def confirm_warehouse_layout(
    warehouse_map_id: int,
    layout_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await db.get(WarehouseLayoutVersion, layout_id)
    if layout is None or layout.warehouse_map_id != warehouse_map_id:
        raise HTTPException(404, "Warehouse layout not found")
    if layout.status != "locked":
        raise HTTPException(409, "Only the locked layout can be confirmed")
    previous_provenance = layout.provenance_status
    layout.provenance_status = "confirmed"
    aisle_ids = select(WarehouseAisle.id).where(WarehouseAisle.layout_version_id == layout.id)
    rack_ids = select(WarehouseRack.id).where(WarehouseRack.aisle_id.in_(aisle_ids))
    shelf_ids = select(WarehouseShelf.id).where(WarehouseShelf.rack_id.in_(rack_ids))
    await db.execute(
        update(WarehouseAisle)
        .where(WarehouseAisle.layout_version_id == layout.id)
        .values(provenance_status="confirmed")
    )
    await db.execute(
        update(WarehouseRack)
        .where(WarehouseRack.aisle_id.in_(aisle_ids))
        .values(provenance_status="confirmed")
    )
    await db.execute(
        update(WarehouseShelf)
        .where(WarehouseShelf.rack_id.in_(rack_ids))
        .values(provenance_status="confirmed")
    )
    await db.execute(
        update(WarehouseBin)
        .where(WarehouseBin.shelf_id.in_(shelf_ids))
        .values(provenance_status="confirmed")
    )
    await db.execute(
        update(WarehouseScanTarget)
        .where(WarehouseScanTarget.layout_version_id == layout.id)
        .values(provenance_status="confirmed")
    )
    await db.commit()
    emit_coordinate_audit(
        event_name="warehouse_layout_confirmed",
        action="confirm_layout",
        resource_type="warehouse_layout",
        resource_id=layout.id,
        warehouse_map_id=warehouse_map_id,
        org_user=org_user,
        reason="operator_confirmed_extracted_layout",
        coordinate_frame_id=layout.coordinate_frame_id,
        old_value={"provenance_status": previous_provenance},
        new_value={"provenance_status": "confirmed"},
        validation_result="pass",
        extra={
            "layout_version": layout.version,
            "artifact_set_id": layout.artifact_set_id,
            "input_checksum": layout.input_checksum,
        },
    )
    return {"layout_id": layout.id, "provenance_status": "confirmed"}
