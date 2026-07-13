from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
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
from backend.modules.warehouse.service.coordinate_audit import emit_coordinate_audit
from backend.modules.warehouse.service.layout import (
    bump_revision,
    parse_revision,
    require_draft_revision,
)
from backend.modules.warehouse.service.scan_to_layout import (
    CandidateInput,
    candidate_status,
    displacement_m,
    persist_candidates,
    review_reasons,
)

router = APIRouter(tags=["warehouse-layout-candidates"])


class LayoutCandidatePage(Page[dict[str, Any]]):
    grouped: dict[str, Any] | None = None


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


class CandidateBatchReviewIn(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=500)
    status: Literal["accepted", "rejected"]


class CandidatePromoteIn(BaseModel):
    candidate_ids: list[int] | None = Field(default=None, max_length=1000)
    revision: int | None = None


def _identity_parts(identity_key: str) -> list[str]:
    return [part for part in str(identity_key or "").replace(":", "/").split("/") if part]


def _review_reasons(row: WarehouseLayoutCandidate) -> list[str]:
    return review_reasons(
        entity_kind=row.entity_kind,
        confidence=float(row.confidence),
        geometry=dict(row.geometry_json or {}),
        displacement=row.displacement_m,
    )


def _group_path(row: WarehouseLayoutCandidate) -> dict:
    parts = _identity_parts(row.identity_key)
    return {
        "aisle_code": parts[0] if len(parts) > 0 else None,
        "rack_code": parts[1] if len(parts) > 1 else None,
        "shelf_level": int(parts[2]) if len(parts) > 2 and str(parts[2]).isdigit() else None,
        "bin_code": parts[3] if len(parts) > 3 else None,
    }


def _out(row: WarehouseLayoutCandidate) -> dict:
    reasons = _review_reasons(row)
    return {
        "id": row.id,
        "layout_version_id": row.layout_version_id,
        "entity_kind": row.entity_kind,
        "identity_key": row.identity_key,
        "group_path": _group_path(row),
        "geometry": row.geometry_json,
        "confidence": row.confidence,
        "status": row.status,
        "review_required": bool(reasons) or row.status == "needs_review",
        "review_reasons": reasons,
        "displacement_m": row.displacement_m,
        "source_sequence": row.source_sequence,
    }


def _grouped(rows: list[WarehouseLayoutCandidate]) -> dict:
    grouped: dict[str, dict] = {}
    for row in rows:
        path = _group_path(row)
        aisle = path["aisle_code"] or "_unassigned"
        rack = path["rack_code"] or "_unassigned"
        shelf = str(path["shelf_level"] if path["shelf_level"] is not None else "_unassigned")
        grouped.setdefault(aisle, {"aisle_code": aisle, "racks": {}})
        grouped[aisle]["racks"].setdefault(rack, {"rack_code": rack, "shelves": {}})
        grouped[aisle]["racks"][rack]["shelves"].setdefault(
            shelf,
            {"shelf_level": path["shelf_level"], "candidates": []},
        )
        grouped[aisle]["racks"][rack]["shelves"][shelf]["candidates"].append(_out(row))
    for aisle_group in grouped.values():
        for rack_group in aisle_group["racks"].values():
            rack_group["shelves"] = list(rack_group["shelves"].values())
        aisle_group["racks"] = list(aisle_group["racks"].values())
    return {"aisles": list(grouped.values())}


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _fit_residual_m(geometry: dict[str, Any]) -> float | None:
    template_fit = geometry.get("template_fit")
    if not isinstance(template_fit, dict):
        template_fit = geometry.get("template_fit_json")
    template_fit = template_fit if isinstance(template_fit, dict) else {}
    values = [
        _float_or_none(geometry.get("fit_residual_m")),
        _float_or_none(template_fit.get("fit_residual_m")),
        _float_or_none(template_fit.get("bay_width_residual_m")),
        _float_or_none(template_fit.get("shelf_level_residual_m")),
    ]
    residuals = [value for value in values if value is not None]
    return max(residuals) if residuals else None


def _apply_candidate_metadata(row, candidate: WarehouseLayoutCandidate) -> None:
    geometry = dict(candidate.geometry_json or {})
    row.confidence = float(candidate.confidence)
    if hasattr(row, "confidence_breakdown_json"):
        row.confidence_breakdown_json = dict(geometry.get("confidence_breakdown") or {})
    for name in ("template_id", "template_version_id", "source_artifact_set_id"):
        if hasattr(row, name):
            setattr(row, name, _int_or_none(geometry.get(name)))
    if hasattr(row, "fitted_transform_json"):
        row.fitted_transform_json = dict(geometry.get("fitted_transform_json") or {})
    if hasattr(row, "template_fit_json"):
        row.template_fit_json = dict(
            geometry.get("template_fit_json") or geometry.get("template_fit") or {}
        )
    if hasattr(row, "fit_residual_m"):
        row.fit_residual_m = _fit_residual_m(geometry)
    if hasattr(row, "observed_point_count"):
        row.observed_point_count = _int_or_none(geometry.get("observed_point_count"))
    if hasattr(row, "coverage_ratio"):
        coverage = _float_or_none(geometry.get("coverage_ratio"))
        row.coverage_ratio = max(0.0, min(1.0, coverage)) if coverage is not None else None
    if hasattr(row, "last_verified_at"):
        row.last_verified_at = candidate.reviewed_at or candidate.created_at or datetime.now(UTC)
    if hasattr(row, "face_plane_json"):
        row.face_plane_json = dict(
            geometry.get("face_plane_json")
            or geometry.get("rack_face_plane")
            or geometry.get("face_plane")
            or {}
        )
    if hasattr(row, "center_local_json"):
        row.center_local_json = dict(
            geometry.get("center_local_json")
            or geometry.get("target_point")
            or geometry.get("center")
            or {}
        )
    if hasattr(row, "volume_json"):
        row.volume_json = dict(geometry.get("volume_json") or geometry.get("volume") or {})


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
