from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseLayoutCandidate,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseShelf,
)
from backend.modules.warehouse.service.scan_to_layout import (
    CandidateInput,
    candidate_status,
    displacement_m,
    persist_candidates,
)

router = APIRouter(tags=["warehouse-layout-candidates"])


class CandidateIn(BaseModel):
    entity_kind: str
    identity_key: str = Field(min_length=1, max_length=256)
    geometry: dict
    confidence: float = Field(ge=0, le=1)
    source_sequence: int | None = Field(default=None, ge=0)


class CandidateBatchIn(BaseModel):
    layout_version_id: int | None = None
    candidates: list[CandidateIn] = Field(min_length=1, max_length=2000)


class CandidateReviewIn(BaseModel):
    status: Literal["accepted", "rejected"]


def _out(row: WarehouseLayoutCandidate) -> dict:
    return {
        "id": row.id,
        "layout_version_id": row.layout_version_id,
        "entity_kind": row.entity_kind,
        "identity_key": row.identity_key,
        "geometry": row.geometry_json,
        "confidence": row.confidence,
        "status": row.status,
        "displacement_m": row.displacement_m,
        "source_sequence": row.source_sequence,
    }


@router.post("/maps/{warehouse_map_id}/layout-candidates/batch", status_code=201)
async def ingest_layout_candidates(
    warehouse_map_id: int,
    payload: CandidateBatchIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    if payload.layout_version_id is not None:
        layout = await db.get(WarehouseLayoutVersion, payload.layout_version_id)
        if (
            layout is None
            or layout.warehouse_map_id != warehouse_map_id
            or layout.status != "draft"
        ):
            raise HTTPException(409, "Candidates require a draft layout from this map")
    rows = await persist_candidates(
        db,
        warehouse_map_id=warehouse_map_id,
        layout_version_id=payload.layout_version_id,
        candidates=[CandidateInput(**item.model_dump()) for item in payload.candidates],
    )
    if rows:
        from backend.modules.warehouse.service.provisional_mapping import note_provisional_update

        confidence = sum(float(row.confidence or 0.0) for row in rows) / len(rows)
        note_provisional_update(
            warehouse_map_id=warehouse_map_id,
            confidence=confidence,
            displacement_m=max(float(row.displacement_m or 0.0) for row in rows),
        )
    await db.commit()
    return {"items": [_out(row) for row in rows], "validation_warnings": []}


@router.get("/maps/{warehouse_map_id}/layout-candidates")
async def list_layout_candidates(
    warehouse_map_id: int,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    query = select(WarehouseLayoutCandidate).where(
        WarehouseLayoutCandidate.warehouse_map_id == warehouse_map_id
    )
    if status:
        query = query.where(WarehouseLayoutCandidate.status == status)
    rows = (await db.execute(query.order_by(WarehouseLayoutCandidate.id))).scalars().all()
    return {"items": [_out(row) for row in rows]}


@router.patch("/maps/{warehouse_map_id}/layout-candidates/{candidate_id}")
async def decide_layout_candidate(
    warehouse_map_id: int,
    candidate_id: int,
    payload: CandidateReviewIn,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    expected = str(if_match or "").strip().removeprefix("W/").strip('"')
    if not expected:
        raise HTTPException(428, "If-Match is required")
    if expected != str(candidate_id):
        raise HTTPException(412, "Candidate revision mismatch")
    row = await db.get(WarehouseLayoutCandidate, candidate_id)
    if row is None or row.warehouse_map_id != warehouse_map_id:
        raise HTTPException(404, "Layout candidate not found")
    row.status = payload.status
    row.reviewed_at = datetime.now(UTC)
    await db.commit()
    return {"item": _out(row), "validation_warnings": []}


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
        row.status = candidate_status(displacement=row.displacement_m, threshold_m=threshold_m)
    await db.commit()
    return {
        "items": [_out(row) for row in candidates],
        "needs_review": sum(row.status == "needs_review" for row in candidates),
        "validation_warnings": [],
    }
