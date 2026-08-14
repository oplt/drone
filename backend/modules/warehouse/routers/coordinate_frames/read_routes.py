"""Warehouse coordinate-frame routes — read/list endpoints."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.warehouse.models import WarehouseCoordinateFrame

from .deps import frame_contract_payload, get_map_or_404
from .helpers import _out
from .router import router
from .schemas import CoordinateFrameOut


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
