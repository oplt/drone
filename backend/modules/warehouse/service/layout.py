from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseRackTemplateVersion,
    WarehouseShelf,
)
from backend.modules.warehouse.service.scan_to_layout import extraction_confidence


@dataclass(frozen=True)
class BinContext:
    layout_version_id: int
    coordinate_frame_id: int
    bin_id: int
    aisle_code: str
    rack_code: str
    shelf_level: int
    bin_code: str


def parse_revision(if_match: str | None, revision: int | None) -> int:
    """Normalize HTTP If-Match (including weak/quoted ETags) or body revision."""
    raw = if_match
    if raw is not None:
        raw = raw.strip()
        if raw.startswith("W/"):
            raw = raw[2:]
        raw = raw.strip('"')
    value = raw if raw else revision
    if value is None:
        raise HTTPException(428, "If-Match header or revision is required")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Invalid layout revision") from exc
    if parsed < 1:
        raise HTTPException(400, "Invalid layout revision")
    return parsed


def require_draft_revision(layout: WarehouseLayoutVersion, expected: int) -> None:
    if layout.status != "draft":
        raise HTTPException(409, "Locked or superseded layouts are immutable")
    if int(layout.revision) != expected:
        raise HTTPException(
            412,
            detail={"code": "revision_mismatch", "expected": expected, "actual": layout.revision},
        )


def bump_revision(layout: WarehouseLayoutVersion) -> int:
    layout.revision = int(layout.revision) + 1
    return int(layout.revision)


def geometry_warnings(geometry: dict | None) -> list[dict[str, str]]:
    if geometry:
        return []
    return [{"code": "geometry_empty", "message": "Entity has no geometry"}]


def can_auto_publish_layout(current: WarehouseLayoutVersion | None) -> bool:
    return current is None or current.provenance_status == "auto"


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


def _template_id(template_meta: dict[str, Any]) -> int | None:
    return _int_or_none(template_meta.get("template_id"))


def _fit_residual_m(template_fit: dict[str, Any]) -> float | None:
    values = [
        _float_or_none(template_fit.get("bay_width_residual_m")),
        _float_or_none(template_fit.get("shelf_level_residual_m")),
        _float_or_none(template_fit.get("fit_residual_m")),
    ]
    residuals = [value for value in values if value is not None]
    return max(residuals) if residuals else None


def _coverage_ratio(template_fit: dict[str, Any]) -> float | None:
    for key in ("coverage_ratio", "template_coverage_ratio"):
        value = _float_or_none(template_fit.get(key))
        if value is not None:
            return max(0.0, min(1.0, value))
    return None


def _observed_point_count(template_meta: dict[str, Any]) -> int | None:
    face_plane = template_meta.get("rack_face_plane")
    if isinstance(face_plane, dict):
        return _int_or_none(face_plane.get("support_points"))
    return None


def _bin_volume_geometry(target, template_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "generated_bin_template",
        "center": dict(getattr(target, "target_point", {}) or {}),
        "frame_id": (getattr(target, "target_point", {}) or {}).get("frame_id"),
        "shelf_level": int(getattr(target, "shelf_level", 0)),
        "bin_count": template_meta.get("rack_template_bin_count"),
        "bay_width_m": template_meta.get("rack_template_bay_width_m"),
    }


def _candidate_breakdown(target) -> dict[str, Any]:
    return dict(getattr(target, "confidence_breakdown", {}) or {})


async def resolve_bin_context(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    bin_id: int | None,
    aisle_code: str,
    rack_code: str | None,
    shelf_level: int | None,
    bin_code: str | None,
) -> BinContext:
    clauses = [
        WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id,
        WarehouseLayoutVersion.status == "locked",
    ]
    if bin_id is not None:
        clauses.append(WarehouseBin.id == bin_id)
    else:
        if rack_code is None or shelf_level is None or bin_code is None:
            raise HTTPException(
                422,
                "Target requires bin_id or complete aisle/rack/shelf/bin identity",
            )
        clauses.extend(
            [
                WarehouseAisle.code == aisle_code,
                WarehouseRack.code == rack_code,
                WarehouseShelf.level == shelf_level,
                WarehouseBin.code == bin_code,
            ]
        )
    row = (
        await db.execute(
            select(
                WarehouseLayoutVersion,
                WarehouseAisle,
                WarehouseRack,
                WarehouseShelf,
                WarehouseBin,
            )
            .join(WarehouseAisle, WarehouseAisle.layout_version_id == WarehouseLayoutVersion.id)
            .join(WarehouseRack, WarehouseRack.aisle_id == WarehouseAisle.id)
            .join(WarehouseShelf, WarehouseShelf.rack_id == WarehouseRack.id)
            .join(WarehouseBin, WarehouseBin.shelf_id == WarehouseShelf.id)
            .where(*clauses)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(409, "Bin does not exist in the locked warehouse layout")
    layout, aisle, rack, shelf, bin_row = row
    return BinContext(
        layout_version_id=int(layout.id),
        coordinate_frame_id=int(layout.coordinate_frame_id),
        bin_id=int(bin_row.id),
        aisle_code=aisle.code,
        rack_code=rack.code,
        shelf_level=int(shelf.level),
        bin_code=bin_row.code,
    )


async def create_extracted_layout(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    coordinate_frame_id: int,
    map_model_id: int,
    artifact_set_id: int,
    input_checksum: str,
    algorithm_version: str,
    targets,
) -> tuple[WarehouseLayoutVersion, dict[tuple[str, str, int, str], int], bool]:
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
    current = (
        await db.execute(
            select(WarehouseLayoutVersion).where(
                WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id,
                WarehouseLayoutVersion.status == "locked",
            )
        )
    ).scalar_one_or_none()
    # Extraction always produces a reviewable draft. Publishing is an explicit,
    # atomic operator action after displacement and revision validation.
    publish = False
    preserved: dict[tuple[str, ...], tuple[dict, str, float | None]] = {}
    if current is not None:
        existing = (
            await db.execute(
                select(WarehouseAisle, WarehouseRack, WarehouseShelf, WarehouseBin)
                .join(WarehouseRack, WarehouseRack.aisle_id == WarehouseAisle.id)
                .join(WarehouseShelf, WarehouseShelf.rack_id == WarehouseRack.id)
                .join(WarehouseBin, WarehouseBin.shelf_id == WarehouseShelf.id)
                .where(
                    WarehouseAisle.layout_version_id == current.id,
                    WarehouseBin.provenance_status.in_(("manual", "confirmed")),
                )
            )
        ).all()
        for aisle, rack, shelf, bin_row in existing:
            key = (aisle.code, rack.code, str(shelf.level), bin_row.code)
            preserved[key] = (
                dict(bin_row.geometry_json or {}),
                bin_row.provenance_status,
                bin_row.confidence,
            )
    confidence_values = [extraction_confidence(target) for target in targets]
    layout_confidence = (
        sum(confidence_values) / len(confidence_values) if confidence_values else None
    )
    layout = WarehouseLayoutVersion(
        warehouse_map_id=warehouse_map_id,
        coordinate_frame_id=coordinate_frame_id,
        map_model_id=map_model_id,
        artifact_set_id=artifact_set_id,
        input_checksum=input_checksum,
        algorithm_version=algorithm_version,
        provenance_status="auto",
        confidence=layout_confidence,
        version=version,
        status="draft",
        source="structure_extraction",
        locked_at=None,
    )
    db.add(layout)
    await db.flush()

    verified_at = datetime.now(UTC)
    by_aisle: dict[str, WarehouseAisle] = {}
    by_rack: dict[tuple[str, str], WarehouseRack] = {}
    by_shelf: dict[tuple[str, str, int], WarehouseShelf] = {}
    bin_ids: dict[tuple[str, str, int, str], int] = {}
    template_id_by_version: dict[int, int | None] = {}

    async def _resolved_template_id(template_meta: dict[str, Any]) -> int | None:
        template_id = _template_id(template_meta)
        if template_id is not None:
            return template_id
        template_version_id = _int_or_none(template_meta.get("template_version_id"))
        if template_version_id is None:
            return None
        if template_version_id not in template_id_by_version:
            version_row = await db.get(WarehouseRackTemplateVersion, template_version_id)
            template_id_by_version[template_version_id] = (
                int(version_row.template_id) if version_row is not None else None
            )
        return template_id_by_version[template_version_id]

    for target in targets:
        confidence = extraction_confidence(target)
        aisle_key = str(target.aisle_code)
        rack_key = (aisle_key, str(target.rack_code))
        shelf_key = (*rack_key, int(target.shelf_level))
        bin_key = (*shelf_key, str(target.bin_code))
        template_meta = dict(getattr(target, "template_metadata", {}) or {})
        template_fit = dict(template_meta.get("template_fit") or {})
        template_id = await _resolved_template_id(template_meta)
        if aisle_key not in by_aisle:
            aisle = WarehouseAisle(
                layout_version_id=layout.id,
                code=aisle_key,
                source_artifact_set_id=artifact_set_id,
                template_id=template_id,
                confidence_breakdown_json=_candidate_breakdown(target),
                fit_residual_m=_fit_residual_m(template_fit),
                observed_point_count=_observed_point_count(template_meta),
                coverage_ratio=_coverage_ratio(template_fit),
                last_verified_at=verified_at,
                confidence=confidence,
            )
            db.add(aisle)
            await db.flush()
            by_aisle[aisle_key] = aisle
        if rack_key not in by_rack:
            template_version_id = template_meta.get("template_version_id")
            rack = WarehouseRack(
                aisle_id=by_aisle[aisle_key].id,
                code=rack_key[1],
                geometry_json={"template": template_meta} if template_meta else {},
                source_artifact_set_id=artifact_set_id,
                template_id=template_id,
                template_version_id=int(template_version_id) if template_version_id else None,
                template_fit_json=template_fit,
                face_plane_json=dict(template_meta.get("rack_face_plane") or {}),
                confidence_breakdown_json=_candidate_breakdown(target),
                fit_residual_m=_fit_residual_m(template_fit),
                observed_point_count=_observed_point_count(template_meta),
                coverage_ratio=_coverage_ratio(template_fit),
                last_verified_at=verified_at,
                confidence=confidence,
            )
            db.add(rack)
            await db.flush()
            by_rack[rack_key] = rack
        if shelf_key not in by_shelf:
            shelf = WarehouseShelf(
                rack_id=by_rack[rack_key].id,
                level=shelf_key[2],
                source_artifact_set_id=artifact_set_id,
                template_id=template_id,
                confidence_breakdown_json=_candidate_breakdown(target),
                fit_residual_m=_fit_residual_m(template_fit),
                observed_point_count=_observed_point_count(template_meta),
                coverage_ratio=_coverage_ratio(template_fit),
                last_verified_at=verified_at,
                confidence=confidence,
            )
            db.add(shelf)
            await db.flush()
            by_shelf[shelf_key] = shelf
        if bin_key not in bin_ids:
            preserved_value = preserved.get((bin_key[0], bin_key[1], str(bin_key[2]), bin_key[3]))
            if preserved_value is not None:
                by_aisle[aisle_key].provenance_status = preserved_value[1]
                by_rack[rack_key].provenance_status = preserved_value[1]
                by_shelf[shelf_key].provenance_status = preserved_value[1]
            bin_row = WarehouseBin(
                shelf_id=by_shelf[shelf_key].id,
                code=bin_key[3],
                geometry_json=(
                    preserved_value[0]
                    if preserved_value is not None
                    else {"target_point": target.target_point, "template": template_meta}
                ),
                source_artifact_set_id=artifact_set_id,
                template_id=template_id,
                center_local_json=dict(getattr(target, "target_point", {}) or {}),
                volume_json=_bin_volume_geometry(target, template_meta),
                confidence_breakdown_json=_candidate_breakdown(target),
                fit_residual_m=_fit_residual_m(template_fit),
                observed_point_count=_observed_point_count(template_meta),
                coverage_ratio=_coverage_ratio(template_fit),
                last_verified_at=verified_at,
                provenance_status=(preserved_value[1] if preserved_value else "auto"),
                confidence=(preserved_value[2] if preserved_value else confidence),
            )
            db.add(bin_row)
            await db.flush()
            bin_ids[bin_key] = int(bin_row.id)
    return layout, bin_ids, publish
