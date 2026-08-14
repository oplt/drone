"""Warehouse layout-candidate routes — displacement review."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_write
from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseLayoutCandidate,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseShelf,
)

from .deps import candidate_status, displacement_m, get_map_or_404
from .helpers import _out
from .router import router


@router.post("/maps/{warehouse_map_id}/layout-versions/{version}/displacement-review")
async def review_layout_displacements(
    warehouse_map_id: int,
    version: int,
    threshold_m: float = 0.25,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = (
        await db.execute(
            select(WarehouseLayoutVersion).where(
                WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id,
                WarehouseLayoutVersion.version == version,
                WarehouseLayoutVersion.status == "draft",
            )
        )
    ).scalar_one_or_none()
    if layout is None:
        raise HTTPException(404, "Draft layout not found")
    locked_rows = (
        await db.execute(
            select(WarehouseAisle, WarehouseRack, WarehouseShelf, WarehouseBin)
            .join(WarehouseRack, WarehouseRack.aisle_id == WarehouseAisle.id)
            .join(WarehouseShelf, WarehouseShelf.rack_id == WarehouseRack.id)
            .join(WarehouseBin, WarehouseBin.shelf_id == WarehouseShelf.id)
            .join(
                WarehouseLayoutVersion,
                WarehouseAisle.layout_version_id == WarehouseLayoutVersion.id,
            )
            .where(
                WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id,
                WarehouseLayoutVersion.status == "locked",
            )
        )
    ).all()
    references = {
        f"{aisle.code}/{rack.code}/{shelf.level}/{bin_row.code}": bin_row.geometry_json
        for aisle, rack, shelf, bin_row in locked_rows
    }
    candidates = (
        (
            await db.execute(
                select(WarehouseLayoutCandidate).where(
                    WarehouseLayoutCandidate.layout_version_id == layout.id
                )
            )
        )
        .scalars()
        .all()
    )
    for row in candidates:
        row.displacement_m = displacement_m(references.get(row.identity_key, {}), row.geometry_json)
        row.status = candidate_status(
            displacement=row.displacement_m,
            threshold_m=threshold_m,
            entity_kind=row.entity_kind,
            confidence=float(row.confidence),
            geometry=dict(row.geometry_json or {}),
        )
    await db.commit()
    return {
        "items": [_out(row) for row in candidates],
        "needs_review": sum(row.status == "needs_review" for row in candidates),
        "validation_warnings": [],
    }
