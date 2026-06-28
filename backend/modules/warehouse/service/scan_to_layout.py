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


def candidate_status(*, displacement: float | None, threshold_m: float = 0.25) -> str:
    return (
        "needs_review" if displacement is not None and displacement > threshold_m else "provisional"
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
                displacement=displacement, threshold_m=displacement_threshold_m
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
