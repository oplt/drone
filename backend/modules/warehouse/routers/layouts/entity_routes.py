"""Warehouse layout routes — entity CRUD."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import assert_map_or_404
from backend.modules.warehouse.service.layout import bump_revision

from .entity_store import _create_entities, _entities
from .helpers import (
    _commit_mutation,
    _entity_dict,
    _layout,
    _mutating_layout,
)
from .router import router
from .schemas import LayoutBatchIn, LayoutEntityIn, LayoutEntityPage, LayoutEntityPatch, LayoutMutationOut


@router.get(
    "/maps/{warehouse_map_id}/layout-versions/{version}/{kind}",
    response_model=LayoutEntityPage,
)
async def list_layout_entities(
    warehouse_map_id: int,
    version: int,
    kind: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _layout(db, warehouse_map_id, version)
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await _entities(
        db,
        layout.id,
        kind,
        limit=page_limit + 1,
        offset=page_offset,
    )
    page = page_from_offset(
        [_entity_dict(row) for row in rows],
        limit=page_limit,
        offset=page_offset,
    )
    return {"revision": layout.revision, **page.model_dump()}


@router.post(
    "/maps/{warehouse_map_id}/layout-versions/{version}/{kind}", response_model=LayoutMutationOut
)
async def create_layout_entity(
    warehouse_map_id: int,
    version: int,
    kind: str,
    payload: LayoutEntityIn,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    if kind not in {"aisles", "racks", "shelves", "bins", "zones"}:
        raise HTTPException(404, "Unknown layout entity")
    layout = await _mutating_layout(db, warehouse_map_id, version, if_match, payload.revision)
    return await _commit_mutation(db, layout, await _create_entities(db, layout, kind, [payload]))


@router.post(
    "/maps/{warehouse_map_id}/layout-versions/{version}/{kind}/batch",
    response_model=LayoutMutationOut,
)
async def create_layout_entity_batch(
    warehouse_map_id: int,
    version: int,
    kind: str,
    payload: LayoutBatchIn,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    if kind not in {"shelves", "bins"}:
        raise HTTPException(404, "Batch supported for shelves/bins")
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _mutating_layout(db, warehouse_map_id, version, if_match, payload.revision)
    return await _commit_mutation(
        db, layout, await _create_entities(db, layout, kind, payload.items)
    )


@router.patch(
    "/maps/{warehouse_map_id}/layout-versions/{version}/{kind}/{entity_id}",
    response_model=LayoutMutationOut,
)
async def patch_layout_entity(
    warehouse_map_id: int,
    version: int,
    kind: str,
    entity_id: int,
    payload: LayoutEntityPatch,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _mutating_layout(db, warehouse_map_id, version, if_match, payload.revision)
    rows = await _entities(db, layout.id, kind)
    row = next((r for r in rows if int(r.id) == entity_id), None)
    if row is None:
        raise HTTPException(404, "Layout entity not found")
    changes = payload.model_dump(exclude_unset=True, exclude={"revision"})
    if "geometry" in changes:
        changes["geometry_json"] = changes.pop("geometry")
    for name, value in changes.items():
        if hasattr(row, name):
            setattr(row, name, value)
    if hasattr(row, "provenance_status"):
        row.provenance_status = "manual"
    await db.flush()
    return await _commit_mutation(db, layout, [row])


@router.delete(
    "/maps/{warehouse_map_id}/layout-versions/{version}/{kind}/{entity_id}",
    response_model=LayoutMutationOut,
)
async def delete_layout_entity(
    warehouse_map_id: int,
    version: int,
    kind: str,
    entity_id: int,
    revision: int | None = None,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _mutating_layout(db, warehouse_map_id, version, if_match, revision)
    row = next((r for r in await _entities(db, layout.id, kind) if int(r.id) == entity_id), None)
    if row is None:
        raise HTTPException(404, "Layout entity not found")
    deleted = _entity_dict(row)
    await db.delete(row)
    new_revision = bump_revision(layout)
    await db.commit()
    return LayoutMutationOut(revision=new_revision, items=[deleted], validation_warnings=[])
