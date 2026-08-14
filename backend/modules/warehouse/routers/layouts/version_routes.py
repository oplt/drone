"""Warehouse layout routes — version lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, Header, HTTPException, Query, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.warehouse.http_access import assert_map_or_404
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
from backend.modules.warehouse.service.coordinate_import_export import (
    export_envelope,
    validate_envelope,
)
from backend.modules.warehouse.service.layout import bump_revision
from backend.shared.json_responses import orjson_response

from .entity_store import _all_entities, _create_entities
from .helpers import (
    _commit_mutation,
    _entity_dict,
    _layout,
    _mutating_layout,
    _publish_block,
    _validation,
)
from .router import router
from .schemas import LayoutEntityIn, LayoutValidationOut, LayoutVersionCreate


@router.get(
    "/maps/{warehouse_map_id}/layout-versions",
    response_model=Page[dict[str, Any]],
)
async def list_layout_versions(
    warehouse_map_id: int,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = (
        (
            await db.execute(
                select(WarehouseLayoutVersion)
                .where(WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id)
                .order_by(WarehouseLayoutVersion.version, WarehouseLayoutVersion.id)
                .offset(page_offset)
                .limit(page_limit + 1)
            )
        )
        .scalars()
        .all()
    )
    items = [
        {
            "id": r.id,
            "version": r.version,
            "revision": r.revision,
            "status": r.status,
            "source": r.source,
        }
        for r in rows
    ]
    return page_from_offset(items, limit=page_limit, offset=page_offset).model_dump()


@router.get("/maps/{warehouse_map_id}/layout-versions/{version}")
async def get_layout_version(
    warehouse_map_id: int,
    version: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
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
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
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
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    return await _validation(await _layout(db, warehouse_map_id, version), db)


@router.post("/maps/{warehouse_map_id}/layout-versions/{version}/publish")
async def publish_layout_version(
    warehouse_map_id: int,
    version: int,
    if_match: str | None = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _mutating_layout(db, warehouse_map_id, version, if_match, None)
    report = await _validation(layout, db)
    if not report.valid:
        raise _publish_block(
            "layout_invalid",
            {"code": "layout_invalid", "issues": report.issues},
            status_code=422,
        )
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
        raise _publish_block(
            "active_missions",
            "Cannot publish layout while missions are planned or running",
        )
    frame = await db.get(WarehouseCoordinateFrame, layout.coordinate_frame_id)
    if frame is None or frame.status != "locked":
        raise _publish_block("coordinate_frame_not_locked", "Layout coordinate frame is not locked")
    if layout.source == "structure_extraction":
        if layout.artifact_set_id is None or layout.map_model_id is None:
            raise _publish_block(
                "missing_artifact_revision",
                "Layout has no pinned scan artifact/model revisions",
            )
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
            raise _publish_block(
                "artifact_revision_mismatch",
                "Layout artifact, model, and frame revisions do not match",
            )
        if artifact.sensor_rig_id is None or not artifact.calibration_hash:
            raise _publish_block(
                "missing_sensor_calibration",
                "Scan artifact has no pinned sensor calibration",
            )
        sensor_rig = await db.get(WarehouseSensorRig, artifact.sensor_rig_id)
        if (
            sensor_rig is None
            or sensor_rig.calibration_status != "valid"
            or sensor_rig.calibration_hash != artifact.calibration_hash
        ):
            raise _publish_block(
                "sensor_calibration_changed",
                "Pinned sensor calibration is unavailable or changed",
            )
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
        raise _publish_block(
            "candidates_require_review",
            f"{review_count} displaced candidates require review",
        )
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
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    layout = await _layout(db, warehouse_map_id, version)
    entities = {
        kind: [_entity_dict(row) for row in rows]
        for kind, rows in (await _all_entities(db, layout.id)).items()
    }
    return orjson_response(
        export_envelope(
            warehouse_map_id=warehouse_map_id,
            layout_version=version,
            revision=layout.revision,
            entities=entities,
        )
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
    await assert_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
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
