"""Warehouse layout routes — shared helpers."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseLayoutVersion
from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
    record_layout_publish_block,
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

from .schemas import LayoutEntityIn, LayoutMutationOut, LayoutValidationOut


def _publish_block(reason: str, detail: object, *, status_code: int = 409) -> HTTPException:
    record_layout_publish_block(reason=reason)
    return HTTPException(status_code, detail)


def _entity_dict(row) -> dict:
    result = {"id": int(row.id)}
    for source, target in (
        ("code", "code"),
        ("level", "level"),
        ("kind", "kind"),
        ("geometry_json", "geometry"),
        ("template_id", "template_id"),
        ("template_version_id", "template_version_id"),
        ("source_artifact_set_id", "source_artifact_set_id"),
        ("fitted_transform_json", "fitted_transform_json"),
        ("template_fit_json", "template_fit_json"),
        ("face_plane_json", "face_plane_json"),
        ("center_local_json", "center_local_json"),
        ("volume_json", "volume_json"),
        ("confidence_breakdown_json", "confidence_breakdown_json"),
        ("fit_residual_m", "fit_residual_m"),
        ("observed_point_count", "observed_point_count"),
        ("coverage_ratio", "coverage_ratio"),
        ("last_verified_at", "last_verified_at"),
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


def _apply_entity_metadata(row, item: LayoutEntityIn) -> None:
    for name in (
        "template_id",
        "template_version_id",
        "source_artifact_set_id",
        "fitted_transform_json",
        "template_fit_json",
        "face_plane_json",
        "center_local_json",
        "volume_json",
        "confidence_breakdown_json",
        "fit_residual_m",
        "observed_point_count",
        "coverage_ratio",
        "last_verified_at",
    ):
        if hasattr(row, name):
            setattr(row, name, getattr(item, name))


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


async def _validation(layout: WarehouseLayoutVersion, db: AsyncSession) -> LayoutValidationOut:
    from .entity_store import _all_entities

    issues = []
    entity_count = 0
    entities = await _all_entities(db, layout.id)
    for kind in ("aisles", "racks", "shelves", "bins", "zones"):
        rows = entities[kind]
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


__all__ = [
    "_apply_entity_metadata",
    "_commit_mutation",
    "_entity_dict",
    "_layout",
    "_mutating_layout",
    "_publish_block",
    "_validation",
]
