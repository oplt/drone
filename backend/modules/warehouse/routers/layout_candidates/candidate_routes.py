"""Warehouse layout-candidate routes — ingest, list, and review."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.models import WarehouseLayoutCandidate, WarehouseLayoutVersion

from .deps import CandidateInput, emit_coordinate_audit, get_map_or_404, persist_candidates
from .helpers import _grouped, _out
from .router import router
from .schemas import (
    CandidateBatchIn,
    CandidateBatchReviewIn,
    CandidateReviewIn,
    LayoutCandidatePage,
)


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


@router.get("/maps/{warehouse_map_id}/layout-candidates", response_model=LayoutCandidatePage)
async def list_layout_candidates(
    warehouse_map_id: int,
    status: str | None = None,
    grouped: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    query = select(WarehouseLayoutCandidate).where(
        WarehouseLayoutCandidate.warehouse_map_id == warehouse_map_id
    )
    if status:
        query = query.where(WarehouseLayoutCandidate.status == status)
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = (
        await db.execute(
            query.order_by(WarehouseLayoutCandidate.id)
            .offset(page_offset)
            .limit(page_limit + 1)
        )
    ).scalars().all()
    page = page_from_offset(
        [_out(row) for row in rows], limit=page_limit, offset=page_offset
    )
    payload = page.model_dump()
    if grouped:
        payload["grouped"] = _grouped(list(rows[:page_limit]))
    return payload


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
    emit_coordinate_audit(
        event_name="warehouse_layout_candidate_reviewed",
        action=f"{payload.status}_layout_candidate",
        resource_type="warehouse_layout_candidate",
        resource_id=row.id,
        warehouse_map_id=warehouse_map_id,
        org_user=org_user,
        reason="operator_reviewed_layout_candidate",
        old_value={"status": "needs_review"},
        new_value=_out(row),
    )
    return {"item": _out(row), "validation_warnings": []}


@router.post("/maps/{warehouse_map_id}/layout-candidates/review")
async def batch_decide_layout_candidates(
    warehouse_map_id: int,
    payload: CandidateBatchReviewIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows = (
        (
            await db.execute(
                select(WarehouseLayoutCandidate).where(
                    WarehouseLayoutCandidate.warehouse_map_id == int(warehouse_map_id),
                    WarehouseLayoutCandidate.id.in_([int(item) for item in payload.candidate_ids]),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != len(set(payload.candidate_ids)):
        raise HTTPException(404, "One or more layout candidates were not found")
    now = datetime.now(UTC)
    for row in rows:
        row.status = payload.status
        row.reviewed_at = now
    await db.commit()
    for row in rows:
        emit_coordinate_audit(
            event_name="warehouse_layout_candidate_reviewed",
            action=f"{payload.status}_layout_candidate",
            resource_type="warehouse_layout_candidate",
            resource_id=row.id,
            warehouse_map_id=warehouse_map_id,
            org_user=org_user,
            reason="operator_batch_reviewed_layout_candidates",
            new_value=_out(row),
        )
    return {"items": [_out(row) for row in rows], "validation_warnings": []}
