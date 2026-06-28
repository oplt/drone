from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseCoordinateFrame,
    WarehouseInspectionMission,
    WarehouseLayoutCandidate,
    WarehouseLayoutVersion,
    WarehouseModel,
    WarehouseRack,
    WarehouseSafetyZone,
    WarehouseScanArtifactSet,
    WarehouseScanTarget,
    WarehouseSensorRig,
    WarehouseShelf,
)
from backend.modules.warehouse.service.coordinate_audit import emit_coordinate_audit
from backend.modules.warehouse.service.coordinate_import_export import (
    export_envelope,
    validate_envelope,
)
from backend.modules.warehouse.service.coordinate_validation import (
    validate_geometry,
    validate_vertical_bounds,
)
from backend.modules.warehouse.service.layout import (
    bump_revision,
    geometry_warnings,
    parse_revision,
    require_draft_revision,
)

router = APIRouter(tags=["warehouse-layouts"])


class LayoutEntityIn(BaseModel):
    parent_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=64)
    level: int | None = None
    kind: str | None = None
    geometry: dict = Field(default_factory=dict)
    min_z_m: float | None = None
    max_z_m: float | None = None
    active: bool = True
    revision: int | None = None


class LayoutEntityPatch(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    level: int | None = None
    kind: str | None = None
    geometry: dict | None = None
    min_z_m: float | None = None
    max_z_m: float | None = None
    active: bool | None = None
    revision: int | None = None


class LayoutMutationOut(BaseModel):
    revision: int
    items: list[dict]
    validation_warnings: list[dict[str, str]]


class LayoutBatchIn(BaseModel):
    items: list[LayoutEntityIn] = Field(min_length=1, max_length=1000)
    revision: int | None = None


class LayoutVersionCreate(BaseModel):
    source: str = Field(default="manual", min_length=1, max_length=64)


class LayoutValidationOut(BaseModel):
    valid: bool
    revision: int
    issues: list[dict]


async def _validation(layout: WarehouseLayoutVersion, db: AsyncSession) -> LayoutValidationOut:
    issues = []
    entity_count = 0
    for kind in ("aisles", "racks", "shelves", "bins", "zones"):
        rows = await _entities(db, layout.id, kind)
        entity_count += len(rows)
        for row in rows:
            issues.extend(
                issue.__dict__
                for issue in validate_geometry(
                    row.geometry_json or {}, path=f"{kind}.{row.id}.geometry"
                )
            )
            if kind == "zones":
                issues.extend(
                    issue.__dict__ for issue in validate_vertical_bounds(row.min_z_m, row.max_z_m)
                )
    if entity_count == 0:
        issues.append(
            {
                "code": "layout_empty",
                "message": "Layout has no entities",
                "path": "entities",
                "severity": "error",
            }
        )
    return LayoutValidationOut(
        valid=not any(issue["severity"] == "error" for issue in issues),
        revision=layout.revision,
        issues=issues,
    )


async def _layout(db: AsyncSession, map_id: int, version: int) -> WarehouseLayoutVersion:
    row = (
        await db.execute(
            select(WarehouseLayoutVersion).where(
                WarehouseLayoutVersion.warehouse_map_id == map_id,
                WarehouseLayoutVersion.version == version,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Warehouse layout version not found")
    return row


def _entity_dict(row) -> dict:
    result = {"id": int(row.id)}
    for source, target in (
        ("code", "code"),
        ("level", "level"),
        ("kind", "kind"),
        ("geometry_json", "geometry"),
        ("min_z_m", "min_z_m"),
        ("max_z_m", "max_z_m"),
        ("active", "active"),
        ("aisle_id", "parent_id"),
        ("rack_id", "parent_id"),
        ("shelf_id", "parent_id"),
    ):
        if hasattr(row, source):
            result[target] = getattr(row, source)
    return result


async def _mutating_layout(db, map_id, version, if_match, revision):
    layout = await _layout(db, map_id, version)
    require_draft_revision(layout, parse_revision(if_match, revision))
    return layout


async def _commit_mutation(db, layout, rows) -> LayoutMutationOut:
    warnings = [w for row in rows for w in geometry_warnings(getattr(row, "geometry_json", {}))]
    revision = bump_revision(layout)
    await db.commit()
    return LayoutMutationOut(
        revision=revision, items=[_entity_dict(row) for row in rows], validation_warnings=warnings
    )


@router.get("/maps/{warehouse_map_id}/layout-versions")
async def list_layout_versions(
    warehouse_map_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    rows = (
        (
            await db.execute(
                select(WarehouseLayoutVersion)
                .where(WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id)
                .order_by(WarehouseLayoutVersion.version)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "version": r.version,
            "revision": r.revision,
            "status": r.status,
            "source": r.source,
        }
        for r in rows
    ]


@router.get("/maps/{warehouse_map_id}/layout-versions/{version}")
async def get_layout_version(
    warehouse_map_id: int,
    version: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    row = await _layout(db, warehouse_map_id, version)
    response.headers["ETag"] = f'"{row.revision}"'
    return {
        "id": row.id,
        "version": row.version,
        "revision": row.revision,
        "status": row.status,
        "source": row.source,
        "coordinate_frame_id": row.coordinate_frame_id,
    }


@router.post("/maps/{warehouse_map_id}/layout-versions", status_code=201)
async def create_layout_version(
    warehouse_map_id: int,
    payload: LayoutVersionCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    frame = (
        await db.execute(
            select(WarehouseCoordinateFrame).where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
        )
    ).scalar_one_or_none()
    if frame is None:
        raise HTTPException(409, "A locked coordinate frame is required")
    version = (
        int(
            (
                await db.execute(
                    select(func.coalesce(func.max(WarehouseLayoutVersion.version), 0)).where(
                        WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id
                    )
                )
            ).scalar_one()
        )
        + 1
    )
    row = WarehouseLayoutVersion(
        warehouse_map_id=warehouse_map_id,
        coordinate_frame_id=frame.id,
        version=version,
        revision=1,
        status="draft",
        source=payload.source.strip(),
        provenance_status="manual",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id,
        "version": row.version,
        "revision": row.revision,
        "status": row.status,
        "validation_warnings": [],
    }


@router.post(
    "/maps/{warehouse_map_id}/layout-versions/{version}/validate",
    response_model=LayoutValidationOut,
)
async def validate_layout_version(
    warehouse_map_id: int,
    version: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> LayoutValidationOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    return await _validation(await _layout(db, warehouse_map_id, version), db)


@router.post("/maps/{warehouse_map_id}/layout-versions/{version}/publish")
async def publish_layout_version(
    warehouse_map_id: int,
    version: int,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _mutating_layout(db, warehouse_map_id, version, if_match, None)
    report = await _validation(layout, db)
    if not report.valid:
        raise HTTPException(422, {"code": "layout_invalid", "issues": report.issues})
    active_missions = int(
        (
            await db.execute(
                select(func.count())
                .select_from(WarehouseInspectionMission)
                .where(
                    WarehouseInspectionMission.warehouse_map_id == warehouse_map_id,
                    WarehouseInspectionMission.status.in_(("planned", "running")),
                )
            )
        ).scalar_one()
    )
    if active_missions:
        raise HTTPException(409, "Cannot publish layout while missions are planned or running")
    frame = await db.get(WarehouseCoordinateFrame, layout.coordinate_frame_id)
    if frame is None or frame.status != "locked":
        raise HTTPException(409, "Layout coordinate frame is not locked")
    if layout.source == "structure_extraction":
        if layout.artifact_set_id is None or layout.map_model_id is None:
            raise HTTPException(409, "Layout has no pinned scan artifact/model revisions")
        artifact = await db.get(WarehouseScanArtifactSet, layout.artifact_set_id)
        model = await db.get(WarehouseModel, layout.map_model_id)
        if (
            artifact is None
            or model is None
            or artifact.coordinate_frame_id != frame.id
            or artifact.map_model_id != model.id
            or model.coordinate_frame_id != frame.id
            or artifact.checksum_sha256 != layout.input_checksum
        ):
            raise HTTPException(409, "Layout artifact, model, and frame revisions do not match")
        if artifact.sensor_rig_id is None or not artifact.calibration_hash:
            raise HTTPException(409, "Scan artifact has no pinned sensor calibration")
        sensor_rig = await db.get(WarehouseSensorRig, artifact.sensor_rig_id)
        if (
            sensor_rig is None
            or sensor_rig.calibration_status != "valid"
            or sensor_rig.calibration_hash != artifact.calibration_hash
        ):
            raise HTTPException(409, "Pinned sensor calibration is unavailable or changed")
    review_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(WarehouseLayoutCandidate)
                .where(
                    WarehouseLayoutCandidate.layout_version_id == layout.id,
                    WarehouseLayoutCandidate.status == "needs_review",
                )
            )
        ).scalar_one()
    )
    if review_count:
        raise HTTPException(409, f"{review_count} displaced candidates require review")
    now = datetime.now(UTC)
    previously_locked_ids = select(WarehouseLayoutVersion.id).where(
        WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id,
        WarehouseLayoutVersion.status == "locked",
    )
    await db.execute(
        update(WarehouseScanTarget)
        .where(WarehouseScanTarget.layout_version_id.in_(previously_locked_ids))
        .values(active=False)
    )
    await db.execute(
        update(WarehouseLayoutVersion)
        .where(
            WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id,
            WarehouseLayoutVersion.status == "locked",
        )
        .values(status="superseded", superseded_at=now)
    )
    layout.status = "locked"
    layout.locked_at = now
    projected_targets = (
        (
            await db.execute(
                select(WarehouseScanTarget).where(
                    WarehouseScanTarget.layout_version_id == layout.id
                )
            )
        )
        .scalars()
        .all()
    )
    for target in projected_targets:
        target.active = (
            target.provenance_status in {"manual", "confirmed"}
            or target.scan_pose_local_json.get("_clearance_status") == "active"
        )
    revision = bump_revision(layout)
    await db.commit()
    return {
        "id": layout.id,
        "version": version,
        "revision": revision,
        "status": "locked",
        "validation_warnings": [issue for issue in report.issues if issue["severity"] == "warning"],
    }


@router.get("/maps/{warehouse_map_id}/layout-versions/{version}/export")
async def export_layout_version(
    warehouse_map_id: int,
    version: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _layout(db, warehouse_map_id, version)
    entities = {
        kind: [_entity_dict(row) for row in await _entities(db, layout.id, kind)]
        for kind in ("aisles", "racks", "shelves", "bins", "zones")
    }
    return export_envelope(
        warehouse_map_id=warehouse_map_id,
        layout_version=version,
        revision=layout.revision,
        entities=entities,
    )


@router.post("/maps/{warehouse_map_id}/layout-versions/{version}/import")
async def import_layout_version(
    warehouse_map_id: int,
    version: int,
    payload: dict,
    dry_run: bool = True,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    try:
        validate_envelope(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if int(payload.get("warehouse_map_id", -1)) != warehouse_map_id:
        raise HTTPException(409, "Import belongs to a different warehouse map")
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        raise HTTPException(422, "Import entities must be an object")
    counts = {
        kind: len(entities.get(kind, []))
        for kind in ("aisles", "racks", "shelves", "bins", "zones")
    }
    if dry_run:
        return {"dry_run": True, "valid": True, "counts": counts, "validation_warnings": []}
    layout = await _mutating_layout(db, warehouse_map_id, version, if_match, None)
    for model in (
        WarehouseScanTarget,
        WarehouseSafetyZone,
        WarehouseBin,
        WarehouseShelf,
        WarehouseRack,
        WarehouseAisle,
    ):
        if model is WarehouseScanTarget or model in (WarehouseSafetyZone, WarehouseAisle):
            await db.execute(delete(model).where(model.layout_version_id == layout.id))
    id_map: dict[int, int] = {}
    for kind in ("aisles", "racks", "shelves", "bins", "zones"):
        items = []
        for raw in entities.get(kind, []):
            item = dict(raw)
            old_id = int(item.pop("id")) if item.get("id") is not None else None
            if item.get("parent_id") is not None:
                item["parent_id"] = id_map.get(int(item["parent_id"]), item["parent_id"])
            parsed = LayoutEntityIn.model_validate(item)
            rows = await _create_entities(db, layout, kind, [parsed])
            if old_id is not None:
                id_map[old_id] = int(rows[0].id)
            items.extend(rows)
    revision = bump_revision(layout)
    await db.commit()
    return {
        "dry_run": False,
        "valid": True,
        "counts": counts,
        "revision": revision,
        "validation_warnings": [],
    }


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
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


async def _entities(db, layout_id: int, kind: str):
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
    return (await db.execute(query)).scalars().all()


@router.get("/maps/{warehouse_map_id}/layout-versions/{version}/{kind}")
async def list_layout_entities(
    warehouse_map_id: int,
    version: int,
    kind: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _layout(db, warehouse_map_id, version)
    return {
        "revision": layout.revision,
        "items": [_entity_dict(r) for r in await _entities(db, layout.id, kind)],
    }


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
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
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
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
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
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
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
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _mutating_layout(db, warehouse_map_id, version, if_match, revision)
    row = next((r for r in await _entities(db, layout.id, kind) if int(r.id) == entity_id), None)
    if row is None:
        raise HTTPException(404, "Layout entity not found")
    deleted = _entity_dict(row)
    await db.delete(row)
    new_revision = bump_revision(layout)
    await db.commit()
    return LayoutMutationOut(revision=new_revision, items=[deleted], validation_warnings=[])


class WarehouseLayoutBinOut(BaseModel):
    id: int
    aisle_code: str
    rack_code: str
    shelf_level: int
    bin_code: str
    geometry: dict


class WarehouseSafetyZoneOut(BaseModel):
    id: int
    code: str
    kind: str
    geometry: dict
    min_z_m: float | None
    max_z_m: float | None
    active: bool


class WarehouseLayoutOut(BaseModel):
    id: int
    warehouse_map_id: int
    coordinate_frame_id: int
    version: int
    revision: int
    status: str
    source: str
    provenance_status: str
    artifact_set_id: int | None
    input_checksum: str | None
    algorithm_version: str | None
    created_at: datetime
    locked_at: datetime | None
    bins: list[WarehouseLayoutBinOut]
    safety_zones: list[WarehouseSafetyZoneOut]


@router.get("/maps/{warehouse_map_id}/layouts/active", response_model=WarehouseLayoutOut)
async def get_active_warehouse_layout(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLayoutOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
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
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
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
