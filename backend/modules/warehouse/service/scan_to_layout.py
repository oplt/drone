"""Scan observations to draft-layout candidates and displacement review."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseLayoutCandidate


@dataclass(frozen=True)
class CandidateInput:
    entity_kind: str
    identity_key: str
    geometry: dict[str, Any]
    confidence: float
    source_sequence: int | None = None


def geometry_anchor(geometry: dict[str, Any]) -> tuple[float, float, float] | None:
    source = (
        geometry.get("target_point") if isinstance(geometry.get("target_point"), dict) else geometry
    )
    keys = (("x_m", "y_m", "z_m"), ("x", "y", "z"))
    for x_key, y_key, z_key in keys:
        values = (source.get(x_key), source.get(y_key), source.get(z_key, 0.0))
        if all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values):
            return tuple(float(value) for value in values)
    return None


def displacement_m(reference: dict[str, Any], observed: dict[str, Any]) -> float | None:
    left, right = geometry_anchor(reference), geometry_anchor(observed)
    if left is None or right is None:
        return None
    return math.dist(left, right)


def _template_bin_mismatch(geometry: dict[str, Any]) -> bool:
    template = geometry.get("template") if isinstance(geometry, dict) else {}
    template = template if isinstance(template, dict) else {}
    expected = template.get("bin_count")
    observed = geometry.get("bin_count") or geometry.get("observed_bin_count")
    if expected is None or observed is None:
        return False
    try:
        return int(expected) != int(observed)
    except (TypeError, ValueError):
        return False


def _missing_clearance_evidence(geometry: dict[str, Any]) -> bool:
    evidence = geometry.get("evidence") if isinstance(geometry, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    quality = geometry.get("quality") if isinstance(geometry, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    if "occupancy_available" in evidence or "esdf_available" in evidence:
        return not bool(evidence.get("occupancy_available") or evidence.get("esdf_available"))
    if "missing_occupancy_grid" in set(quality.get("reasons") or []):
        return True
    if "missing_esdf_topic" in set(quality.get("reasons") or []):
        return True
    return False


def review_reasons(
    *,
    entity_kind: str,
    confidence: float,
    geometry: dict[str, Any] | None = None,
    displacement: float | None = None,
    displacement_threshold_m: float = 0.25,
    low_confidence_threshold: float = 0.75,
) -> list[str]:
    geometry = geometry or {}
    reasons: list[str] = []
    if entity_kind == "rack" and displacement is None:
        reasons.append("new_rack_row")
    if displacement is not None and displacement > displacement_threshold_m:
        reasons.append("large_displacement")
    if float(confidence) < low_confidence_threshold:
        reasons.append("low_confidence")
    if _missing_clearance_evidence(geometry):
        reasons.append("missing_esdf_or_occupancy_evidence")
    if _template_bin_mismatch(geometry):
        reasons.append("bin_count_mismatch_vs_template")
    return reasons


def candidate_status(
    *,
    displacement: float | None,
    threshold_m: float = 0.25,
    entity_kind: str = "bin",
    confidence: float = 1.0,
    geometry: dict[str, Any] | None = None,
) -> str:
    return (
        "needs_review"
        if review_reasons(
            entity_kind=entity_kind,
            confidence=confidence,
            geometry=geometry,
            displacement=displacement,
            displacement_threshold_m=threshold_m,
        )
        else "provisional"
    )


async def persist_candidates(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    candidates: list[CandidateInput],
    layout_version_id: int | None = None,
    confirmed_geometry: dict[str, dict[str, Any]] | None = None,
    displacement_threshold_m: float = 0.25,
) -> list[WarehouseLayoutCandidate]:
    confirmed_geometry = confirmed_geometry or {}
    rows = []
    for candidate in candidates:
        confidence = max(0.0, min(1.0, float(candidate.confidence)))
        displacement = displacement_m(
            confirmed_geometry.get(candidate.identity_key, {}), candidate.geometry
        )
        row = WarehouseLayoutCandidate(
            warehouse_map_id=warehouse_map_id,
            layout_version_id=layout_version_id,
            entity_kind=candidate.entity_kind,
            identity_key=candidate.identity_key,
            geometry_json=candidate.geometry,
            confidence=confidence,
            status=candidate_status(
                displacement=displacement,
                threshold_m=displacement_threshold_m,
                entity_kind=candidate.entity_kind,
                confidence=confidence,
                geometry=candidate.geometry,
            ),
            displacement_m=displacement,
            source_sequence=candidate.source_sequence,
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


def extraction_confidence(target: Any, fallback: float = 0.5) -> float:
    value = getattr(target, "confidence", None)
    if value is None:
        clearance = getattr(target, "clearance_status", None)
        value = 0.9 if clearance == "active" else 0.55 if clearance == "needs_review" else fallback
    return max(0.0, min(1.0, float(value)))
