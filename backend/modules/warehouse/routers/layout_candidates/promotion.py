"""Warehouse layout-candidate routes — promote accepted candidates into layout entities."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseLayoutCandidate,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseShelf,
)

from .helpers import _apply_candidate_metadata, _identity_parts


async def _draft_layout(
    db: AsyncSession,
    warehouse_map_id: int,
    version: int,
) -> WarehouseLayoutVersion:
    layout = (
        await db.execute(
            select(WarehouseLayoutVersion).where(
                WarehouseLayoutVersion.warehouse_map_id == int(warehouse_map_id),
                WarehouseLayoutVersion.version == int(version),
            )
        )
    ).scalar_one_or_none()
    if layout is None:
        raise HTTPException(404, "Draft layout not found")
    return layout


async def _get_or_create_aisle(
    db: AsyncSession,
    *,
    layout_id: int,
    code: str,
    geometry: dict | None = None,
) -> WarehouseAisle:
    row = (
        await db.execute(
            select(WarehouseAisle).where(
                WarehouseAisle.layout_version_id == int(layout_id),
                WarehouseAisle.code == code,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = WarehouseAisle(
            layout_version_id=int(layout_id),
            code=code,
            geometry_json=geometry or {},
            provenance_status="confirmed",
        )
        db.add(row)
        await db.flush()
    return row


async def _get_or_create_rack(
    db: AsyncSession,
    *,
    aisle: WarehouseAisle,
    code: str,
    geometry: dict | None = None,
) -> WarehouseRack:
    row = (
        await db.execute(
            select(WarehouseRack).where(
                WarehouseRack.aisle_id == int(aisle.id),
                WarehouseRack.code == code,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = WarehouseRack(
            aisle_id=int(aisle.id),
            code=code,
            geometry_json=geometry or {},
            provenance_status="confirmed",
        )
        db.add(row)
        await db.flush()
    return row


async def _get_or_create_shelf(
    db: AsyncSession,
    *,
    rack: WarehouseRack,
    level: int,
    geometry: dict | None = None,
) -> WarehouseShelf:
    row = (
        await db.execute(
            select(WarehouseShelf).where(
                WarehouseShelf.rack_id == int(rack.id),
                WarehouseShelf.level == int(level),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = WarehouseShelf(
            rack_id=int(rack.id),
            level=int(level),
            geometry_json=geometry or {},
            provenance_status="confirmed",
        )
        db.add(row)
        await db.flush()
    return row


async def _promote_candidate(
    db: AsyncSession,
    *,
    layout: WarehouseLayoutVersion,
    candidate: WarehouseLayoutCandidate,
) -> tuple[str, int, dict, dict]:
    parts = _identity_parts(candidate.identity_key)
    geometry = dict(candidate.geometry_json or {})
    if candidate.entity_kind == "aisle":
        if len(parts) < 1:
            raise HTTPException(422, "Aisle candidate identity must include aisle code")
        row = await _get_or_create_aisle(db, layout_id=int(layout.id), code=parts[0])
        old = dict(row.geometry_json or {})
        row.geometry_json = geometry
        row.provenance_status = "confirmed"
        _apply_candidate_metadata(row, candidate)
        return "warehouse_aisle", int(row.id), old, geometry
    if candidate.entity_kind == "rack":
        if len(parts) < 2:
            raise HTTPException(422, "Rack candidate identity must include aisle/rack")
        aisle = await _get_or_create_aisle(db, layout_id=int(layout.id), code=parts[0])
        row = await _get_or_create_rack(db, aisle=aisle, code=parts[1])
        old = dict(row.geometry_json or {})
        row.geometry_json = geometry
        row.provenance_status = "confirmed"
        _apply_candidate_metadata(row, candidate)
        return "warehouse_rack", int(row.id), old, geometry
    if candidate.entity_kind == "shelf":
        if len(parts) < 3:
            raise HTTPException(422, "Shelf candidate identity must include aisle/rack/level")
        aisle = await _get_or_create_aisle(db, layout_id=int(layout.id), code=parts[0])
        rack = await _get_or_create_rack(db, aisle=aisle, code=parts[1])
        shelf = await _get_or_create_shelf(db, rack=rack, level=int(parts[2]))
        old = dict(shelf.geometry_json or {})
        shelf.geometry_json = geometry
        shelf.provenance_status = "confirmed"
        _apply_candidate_metadata(shelf, candidate)
        return "warehouse_shelf", int(shelf.id), old, geometry
    if candidate.entity_kind in {"bin", "inspection_target"}:
        if len(parts) < 4:
            raise HTTPException(422, "Bin candidate identity must include aisle/rack/level/bin")
        aisle = await _get_or_create_aisle(db, layout_id=int(layout.id), code=parts[0])
        rack = await _get_or_create_rack(db, aisle=aisle, code=parts[1])
        shelf = await _get_or_create_shelf(db, rack=rack, level=int(parts[2]))
        row = (
            await db.execute(
                select(WarehouseBin).where(
                    WarehouseBin.shelf_id == int(shelf.id),
                    WarehouseBin.code == parts[3],
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = WarehouseBin(
                shelf_id=int(shelf.id),
                code=parts[3],
                geometry_json={},
                provenance_status="confirmed",
            )
            db.add(row)
            await db.flush()
        old = dict(row.geometry_json or {})
        row.geometry_json = geometry
        row.provenance_status = "confirmed"
        _apply_candidate_metadata(row, candidate)
        return "warehouse_bin", int(row.id), old, geometry
    raise HTTPException(422, f"Unsupported candidate kind: {candidate.entity_kind}")


__all__ = ["_draft_layout", "_promote_candidate"]
