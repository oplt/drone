"""Pure approved-zone export serialization with complete source lineage."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def filter_intervention_zones_by_current_sources(
    zones: Iterable[Any], observations: Iterable[Any], *, run_id: str
) -> tuple[list[Any], list[str]]:
    confirmed_ids = {
        str(row.id)
        for row in observations
        if str(row.run_id) == run_id
        and row.review_state == "confirmed"
        and not getattr(row, "merged_into_id", None)
    }
    eligible: list[Any] = []
    excluded: list[str] = []
    for zone in zones:
        source_ids = {str(value) for value in zone.source_observation_ids}
        if source_ids and source_ids.issubset(confirmed_ids):
            eligible.append(zone)
        else:
            excluded.append(str(zone.id))
    return eligible, excluded


def build_intervention_zone_export(
    zones: Iterable[Any],
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    rows = list(zones)
    if not rows or any(row.status != "approved" for row in rows):
        raise ValueError("approved_intervention_zone_required")
    source_ids = [str(value) for zone in rows for value in [zone.id, *zone.source_observation_ids]]
    features = [
        {
            "type": "Feature",
            "geometry": zone.geometry_geojson,
            "properties": {
                "id": zone.id,
                "name": zone.name,
                "issue_type": zone.category,
                "category": zone.category,
                "area_m2": zone.area_m2,
                "status": zone.status,
                "source_ids": zone.source_observation_ids,
                "evidence_ids": zone.evidence_ids,
                "model_versions": zone.model_versions,
                "reviewed_by_user_id": zone.reviewed_by_user_id,
                "reviewed_at": zone.reviewed_at.isoformat() if zone.reviewed_at else None,
                "source_run_id": zone.run_id,
            },
        }
        for zone in rows
    ]
    metadata = {
        "intervention_zone_ids": [zone.id for zone in rows],
        "source_models": sorted({str(version) for zone in rows for version in zone.model_versions}),
        "reviewer_user_ids": sorted(
            {zone.reviewed_by_user_id for zone in rows if zone.reviewed_by_user_id is not None}
        ),
        "approval_status": "approved",
        "candidate_exclusion_policy": "approved_zones_from_confirmed_observations_only",
    }
    return source_ids, features, metadata
