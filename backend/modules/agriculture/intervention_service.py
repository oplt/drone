"""Creation, editing and explicit approval of evidence-linked intervention zones."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from geoalchemy2.shape import to_shape
from shapely import affinity
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.intervention_models import AgricultureInterventionZone
from backend.modules.agriculture.models import (
    AgricultureAnalysisRun,
    AgricultureFlight,
    AgricultureObservation,
)
from backend.modules.agriculture.p5_models import AgricultureGovernanceAudit


class InterventionZoneConflict(ValueError):
    pass


def normalized_zone_geometry(value: dict[str, Any]):
    geometry = value.get("geometry") if value.get("type") == "Feature" else value
    try:
        parsed = shape(geometry)
    except (TypeError, ValueError) as exc:
        raise ValueError("intervention_zone_geometry_invalid") from exc
    if not parsed.is_valid:
        parsed = parsed.buffer(0)
    if parsed.is_empty or parsed.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("intervention_zone_polygon_required")
    return parsed


def zone_area_m2(geometry) -> float:
    latitude = float(geometry.centroid.y)
    scaled = affinity.scale(
        geometry,
        xfact=111_320.0 * max(0.1, math.cos(math.radians(latitude))),
        yfact=110_574.0,
        origin=(0, 0),
    )
    return float(abs(scaled.area))


class AgricultureInterventionZoneService:
    async def _audit(
        self,
        db: AsyncSession,
        *,
        zone: AgricultureInterventionZone,
        user_id: int | None,
        action: str,
        from_status: str | None = None,
        to_status: str | None = None,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        db.add(
            AgricultureGovernanceAudit(
                org_id=zone.org_id,
                entity_type="intervention_zone",
                entity_id=zone.id,
                actor_user_id=user_id,
                action=action,
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                payload=payload or {},
            )
        )

    async def create(
        self,
        db: AsyncSession,
        *,
        run: AgricultureAnalysisRun,
        flight: AgricultureFlight,
        field: Any,
        name: str,
        category: str,
        observation_ids: list[str],
        user_id: int | None,
        org_id: int | None,
    ) -> AgricultureInterventionZone:
        unique_ids = list(dict.fromkeys(observation_ids))
        rows = list(
            (
                await db.scalars(
                    select(AgricultureObservation).where(
                        AgricultureObservation.id.in_(unique_ids),
                        AgricultureObservation.run_id == run.id,
                        AgricultureObservation.review_state == "confirmed",
                        AgricultureObservation.merged_into_id.is_(None),
                    )
                )
            ).all()
        )
        if len(rows) != len(unique_ids):
            raise ValueError("all_source_observations_must_be_current_confirmed_findings")
        geometries = [normalized_zone_geometry(row.geometry_geojson or {}) for row in rows]
        merged = unary_union(geometries)
        clipped = False
        if getattr(field, "boundary", None) is not None:
            boundary = to_shape(field.boundary)
            if not boundary.covers(merged):
                merged = merged.intersection(boundary)
                clipped = True
        merged = normalized_zone_geometry(mapping(merged))
        zone = AgricultureInterventionZone(
            org_id=org_id,
            field_id=flight.field_id,
            flight_id=flight.id,
            run_id=run.id,
            name=name.strip(),
            category=category.strip(),
            geometry_geojson=mapping(merged),
            area_m2=zone_area_m2(merged),
            source_observation_ids=unique_ids,
            evidence_ids=sorted({str(item) for row in rows for item in (row.evidence_ids or [])}),
            model_versions=sorted({row.model_version for row in rows if row.model_version}),
            status="proposed",
            created_by_user_id=user_id,
        )
        db.add(zone)
        await db.flush()
        await self._audit(
            db,
            zone=zone,
            user_id=user_id,
            action="created",
            to_status="proposed",
            payload={
                "source_observation_ids": unique_ids,
                "evidence_ids": zone.evidence_ids,
                "model_versions": zone.model_versions,
                "geometry_policy": "union_confirmed_sources_clipped_to_field"
                if clipped
                else "union_confirmed_sources",
            },
        )
        await db.commit()
        await db.refresh(zone)
        return zone

    async def update(
        self,
        db: AsyncSession,
        *,
        zone: AgricultureInterventionZone,
        field: Any,
        values: dict[str, Any],
        user_id: int | None,
    ) -> AgricultureInterventionZone:
        if zone.status != "proposed":
            raise InterventionZoneConflict("approved_or_rejected_zone_is_immutable")
        expected_revision = int(values.pop("expected_revision"))
        if expected_revision != zone.revision:
            raise InterventionZoneConflict("intervention_zone_revision_conflict")
        changed: list[str] = []
        for key in ("name", "category"):
            if values.get(key) is not None and getattr(zone, key) != values[key].strip():
                setattr(zone, key, values[key].strip())
                changed.append(key)
        if values.get("geometry_geojson") is not None:
            geometry = normalized_zone_geometry(values["geometry_geojson"])
            if getattr(field, "boundary", None) is not None and not to_shape(field.boundary).covers(
                geometry
            ):
                raise ValueError("intervention_zone_must_stay_within_field_boundary")
            zone.geometry_geojson = mapping(geometry)
            zone.area_m2 = zone_area_m2(geometry)
            changed.extend(["geometry_geojson", "area_m2"])
        if not changed:
            return zone
        zone.revision += 1
        await self._audit(
            db,
            zone=zone,
            user_id=user_id,
            action="edited",
            from_status=zone.status,
            to_status=zone.status,
            payload={"changed_fields": changed, "revision": zone.revision},
        )
        await db.commit()
        await db.refresh(zone)
        return zone

    async def review(
        self,
        db: AsyncSession,
        *,
        zone: AgricultureInterventionZone,
        status: str,
        note: str,
        expected_revision: int,
        user_id: int | None,
    ) -> AgricultureInterventionZone:
        if zone.status != "proposed":
            raise InterventionZoneConflict("intervention_zone_already_reviewed")
        if expected_revision != zone.revision:
            raise InterventionZoneConflict("intervention_zone_revision_conflict")
        if status == "approved":
            confirmed_ids = set(
                (
                    await db.scalars(
                        select(AgricultureObservation.id).where(
                            AgricultureObservation.id.in_(zone.source_observation_ids),
                            AgricultureObservation.run_id == zone.run_id,
                            AgricultureObservation.review_state == "confirmed",
                            AgricultureObservation.merged_into_id.is_(None),
                        )
                    )
                ).all()
            )
            if confirmed_ids != set(zone.source_observation_ids):
                raise ValueError("source_observations_are_no_longer_all_confirmed")
        previous = zone.status
        zone.status = status
        zone.review_note = note.strip()
        zone.reviewed_by_user_id = user_id
        zone.reviewed_at = datetime.now(UTC)
        zone.revision += 1
        await self._audit(
            db,
            zone=zone,
            user_id=user_id,
            action="reviewed",
            from_status=previous,
            to_status=status,
            reason=zone.review_note,
            payload={"revision": zone.revision, "operationally_eligible": status == "approved"},
        )
        await db.commit()
        await db.refresh(zone)
        return zone


agriculture_intervention_zone_service = AgricultureInterventionZoneService()
