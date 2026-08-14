"""Warehouse layout-candidate routes — promote accepted candidates."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_write
from backend.modules.warehouse.models import WarehouseLayoutCandidate

from .deps import (
    bump_revision,
    emit_coordinate_audit,
    get_map_or_404,
    parse_revision,
    require_draft_revision,
)
from .helpers import _out
from .promotion import _draft_layout, _promote_candidate
from .router import router
from .schemas import CandidatePromoteIn


@router.post("/maps/{warehouse_map_id}/layout-versions/{version}/candidates/promote")
async def promote_accepted_layout_candidates(
    warehouse_map_id: int,
    version: int,
    payload: CandidatePromoteIn,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _draft_layout(db, warehouse_map_id, version)
    require_draft_revision(layout, parse_revision(if_match, payload.revision))
    query = select(WarehouseLayoutCandidate).where(
        WarehouseLayoutCandidate.warehouse_map_id == int(warehouse_map_id),
        WarehouseLayoutCandidate.layout_version_id == int(layout.id),
        WarehouseLayoutCandidate.status == "accepted",
    )
    if payload.candidate_ids:
        query = query.where(
            WarehouseLayoutCandidate.id.in_([int(item) for item in payload.candidate_ids])
        )
    candidates = (await db.execute(query.order_by(WarehouseLayoutCandidate.id))).scalars().all()
    if not candidates:
        raise HTTPException(409, "No accepted candidates are available to promote")
    promoted = []
    for candidate in candidates:
        resource_type, resource_id, old_value, new_value = await _promote_candidate(
            db,
            layout=layout,
            candidate=candidate,
        )
        candidate.reviewed_at = candidate.reviewed_at or datetime.now(UTC)
        promoted.append((candidate, resource_type, resource_id, old_value, new_value))
    revision = bump_revision(layout)
    await db.commit()
    for candidate, resource_type, resource_id, old_value, new_value in promoted:
        emit_coordinate_audit(
            event_name="warehouse_layout_candidate_promoted",
            action="promote_layout_candidate",
            resource_type=resource_type,
            resource_id=resource_id,
            warehouse_map_id=warehouse_map_id,
            org_user=org_user,
            reason="operator_promoted_accepted_layout_candidate",
            coordinate_frame_id=layout.coordinate_frame_id,
            old_value=old_value,
            new_value=new_value,
            extra={"candidate_id": int(candidate.id), "layout_version": int(layout.version)},
        )
    return {
        "revision": revision,
        "promoted_count": len(promoted),
        "items": [_out(candidate) for candidate, *_rest in promoted],
        "validation_warnings": [],
    }
