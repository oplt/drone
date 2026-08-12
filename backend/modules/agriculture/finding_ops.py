"""Finding merge/split and field-outcome helpers for PROD-001."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.models import AgricultureObservation
from backend.modules.agriculture.p5_models import AgricultureFieldOutcome, AgricultureGovernanceAudit


def _safe_shape(geojson: dict[str, Any] | None):
    if not geojson:
        return None
    try:
        candidate = geojson.get("geometry") if geojson.get("type") == "Feature" else geojson
        geom = shape(candidate)
        return None if geom.is_empty else geom
    except Exception:
        return None


def merge_observations(
    primary: AgricultureObservation,
    members: list[AgricultureObservation],
) -> AgricultureObservation:
    """Merge member findings into primary without dropping evidence ids."""
    geometries = []
    evidence: list[Any] = list(primary.evidence_ids or [])
    member_ids = list(getattr(primary, "member_observation_ids", None) or [])
    for member in members:
        if member.id == primary.id:
            continue
        member.merged_into_id = primary.id
        member.review_state = "rejected"
        member.review_note = f"Merged into finding {primary.id}"
        member.reviewed_at = datetime.now(UTC)
        member_ids.append(member.id)
        evidence.extend(member.evidence_ids or [])
        geom = _safe_shape(member.geometry_geojson)
        if geom is not None:
            geometries.append(geom)
        primary.severity = max(float(primary.severity or 0), float(member.severity or 0))
        primary.confidence = max(float(primary.confidence or 0), float(member.confidence or 0))
        if member.area_m2 is not None:
            primary.area_m2 = float(primary.area_m2 or 0) + float(member.area_m2)
    primary_geom = _safe_shape(primary.geometry_geojson)
    if primary_geom is not None:
        geometries.insert(0, primary_geom)
    if geometries:
        primary.geometry_geojson = mapping(unary_union(geometries))
    # Preserve order while deduplicating.
    seen: set[str] = set()
    deduped: list[Any] = []
    for item in evidence:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    primary.evidence_ids = deduped
    primary.member_observation_ids = sorted(set(member_ids))
    primary.provenance = {
        **(primary.provenance or {}),
        "merge": {
            "member_observation_ids": primary.member_observation_ids,
            "merged_at": datetime.now(UTC).isoformat(),
        },
    }
    return primary


def split_observation(
    source: AgricultureObservation,
    parts: list[dict[str, Any]],
    *,
    new_id_factory,
) -> list[AgricultureObservation]:
    """Split one finding into new observations that retain provenance to the source."""
    created: list[AgricultureObservation] = []
    for index, part in enumerate(parts):
        geometry = part.get("geometry_geojson") or {}
        row = AgricultureObservation(
            id=new_id_factory(),
            run_id=source.run_id,
            flight_id=source.flight_id,
            field_id=source.field_id,
            observation_type=str(part.get("observation_type") or source.observation_type),
            geometry_geojson=geometry,
            zone_kind=source.zone_kind,
            georef_status=source.georef_status,
            area_m2=part.get("area_m2"),
            severity=float(part.get("severity", source.severity) or 0),
            confidence=float(part.get("confidence", source.confidence) or 0),
            uncertainty={**(source.uncertainty or {}), "split_index": index},
            provenance={
                **(source.provenance or {}),
                "split_from_id": source.id,
            },
            first_detected=source.first_detected,
            last_detected=source.last_detected,
            trend=source.trend,
            evidence_ids=list(part.get("evidence_ids") or source.evidence_ids or []),
            sensor_values=dict(source.sensor_values or {}),
            model_version=source.model_version,
            review_state="unreviewed",
            split_from_id=source.id,
        )
        created.append(row)
    source.review_note = (source.review_note or "") + f" Split into {len(created)} finding(s)."
    source.provenance = {
        **(source.provenance or {}),
        "split_into_ids": [row.id for row in created],
        "split_at": datetime.now(UTC).isoformat(),
    }
    return created


async def record_field_outcome(
    db: AsyncSession,
    *,
    org_id: int | None,
    field_id: int,
    flight_id: str,
    run_id: str,
    observation_id: str,
    outcome_status: str,
    notes: str | None,
    model_version: str | None,
    capability_release_id: str | None,
    user_id: int | None,
) -> AgricultureFieldOutcome:
    """Persist scout/field outcome feedback for later evaluation (never auto-retrain)."""
    row = AgricultureFieldOutcome(
        org_id=org_id,
        field_id=field_id,
        flight_id=flight_id,
        run_id=run_id,
        observation_id=observation_id,
        outcome_status=outcome_status,
        notes=notes,
        model_version=model_version,
        capability_release_id=capability_release_id,
        created_by_user_id=user_id,
    )
    db.add(row)
    db.add(
        AgricultureGovernanceAudit(
            org_id=org_id,
            entity_type="field_outcome",
            entity_id=observation_id,
            actor_user_id=user_id,
            action="outcome_recorded",
            to_status=outcome_status,
            reason=notes,
            payload={
                "observation_id": observation_id,
                "model_version": model_version,
                "capability_release_id": capability_release_id,
                "retraining": False,
            },
        )
    )
    await db.flush()
    return row
