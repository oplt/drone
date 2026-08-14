"""Warehouse layout routes — entity persistence queries."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseRack,
    WarehouseSafetyZone,
    WarehouseShelf,
)

from .helpers import _apply_entity_metadata
from .schemas import LayoutEntityIn


async def _parent_in_layout(db, model, row_id, layout_id):
    if model is WarehouseAisle:
        clauses = [WarehouseAisle.id == row_id, WarehouseAisle.layout_version_id == layout_id]
    elif model is WarehouseRack:
        clauses = [WarehouseRack.id == row_id, WarehouseAisle.layout_version_id == layout_id]
    else:
        clauses = [WarehouseShelf.id == row_id, WarehouseAisle.layout_version_id == layout_id]
    query = select(model).where(*clauses)
    if model is WarehouseRack:
        query = query.join(WarehouseAisle, WarehouseRack.aisle_id == WarehouseAisle.id)
    elif model is WarehouseShelf:
        query = query.join(WarehouseRack, WarehouseShelf.rack_id == WarehouseRack.id).join(
            WarehouseAisle, WarehouseRack.aisle_id == WarehouseAisle.id
        )
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise HTTPException(422, "Parent does not belong to layout version")
    return row


async def _create_entities(db, layout, kind: str, payloads):
    rows = []
    for item in payloads:
        if kind == "aisles":
            if not item.code:
                raise HTTPException(422, "code is required")
            row = WarehouseAisle(
                layout_version_id=layout.id,
                code=item.code,
                geometry_json=item.geometry,
                provenance_status="manual",
            )
        elif kind == "racks":
            await _parent_in_layout(db, WarehouseAisle, item.parent_id, layout.id)
            if not item.code:
                raise HTTPException(422, "code is required")
            row = WarehouseRack(
                aisle_id=item.parent_id,
                code=item.code,
                geometry_json=item.geometry,
                provenance_status="manual",
            )
        elif kind == "shelves":
            await _parent_in_layout(db, WarehouseRack, item.parent_id, layout.id)
            if item.level is None:
                raise HTTPException(422, "level is required")
            row = WarehouseShelf(
                rack_id=item.parent_id,
                level=item.level,
                geometry_json=item.geometry,
                provenance_status="manual",
            )
        elif kind == "bins":
            await _parent_in_layout(db, WarehouseShelf, item.parent_id, layout.id)
            if not item.code:
                raise HTTPException(422, "code is required")
            row = WarehouseBin(
                shelf_id=item.parent_id,
                code=item.code,
                geometry_json=item.geometry,
                provenance_status="manual",
            )
        else:
            if not item.code or not item.kind:
                raise HTTPException(422, "code and kind required")
            row = WarehouseSafetyZone(
                layout_version_id=layout.id,
                code=item.code,
                kind=item.kind,
                geometry_json=item.geometry,
                min_z_m=item.min_z_m,
                max_z_m=item.max_z_m,
                active=item.active,
            )
        _apply_entity_metadata(row, item)
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


async def _all_entities(db: AsyncSession, layout_id: int) -> dict[str, list]:
    kinds = ("aisles", "racks", "shelves", "bins", "zones")
    rows = await asyncio.gather(*(_entities(db, layout_id, kind) for kind in kinds))
    return dict(zip(kinds, rows, strict=True))


async def _entities(
    db: AsyncSession,
    layout_id: int,
    kind: str,
    *,
    limit: int | None = None,
    offset: int = 0,
):
    if kind == "aisles":
        query = select(WarehouseAisle).where(WarehouseAisle.layout_version_id == layout_id)
    elif kind == "racks":
        query = (
            select(WarehouseRack)
            .join(WarehouseAisle)
            .where(WarehouseAisle.layout_version_id == layout_id)
        )
    elif kind == "shelves":
        query = (
            select(WarehouseShelf)
            .join(WarehouseRack)
            .join(WarehouseAisle)
            .where(WarehouseAisle.layout_version_id == layout_id)
        )
    elif kind == "bins":
        query = (
            select(WarehouseBin)
            .join(WarehouseShelf)
            .join(WarehouseRack)
            .join(WarehouseAisle)
            .where(WarehouseAisle.layout_version_id == layout_id)
        )
    elif kind == "zones":
        query = select(WarehouseSafetyZone).where(
            WarehouseSafetyZone.layout_version_id == layout_id
        )
    else:
        raise HTTPException(404, "Unknown layout entity")
    query = query.order_by(*[column.asc() for column in query.selected_columns if column.name == "id"])
    if limit is not None:
        query = query.offset(max(0, offset)).limit(max(1, limit))
    return (await db.execute(query)).scalars().all()


__all__ = ["_all_entities", "_create_entities", "_entities", "_parent_in_layout"]
