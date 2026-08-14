"""Warehouse layout-candidate routes — serialization and metadata helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.modules.warehouse.models import WarehouseLayoutCandidate

from .deps import review_reasons


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


__all__ = [
    "_apply_candidate_metadata",
    "_grouped",
    "_identity_parts",
    "_out",
]
