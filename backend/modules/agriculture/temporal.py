"""Deterministic field-flight alignment and observation change detection."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from shapely.geometry import GeometryCollection, shape
from shapely.ops import unary_union
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.comparability import score_comparability
from backend.modules.agriculture.models import AgricultureAnalysisLayer, AgricultureAnalysisRun, AgricultureFlight, AgricultureObservation
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.temporal_models import AgricultureFlightAlignment, AgricultureObservationChange


def stable_temporal_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:32]


def _geometry(value: dict[str, Any] | None):
    if not value:
        return GeometryCollection()
    try:
        candidate = value.get("geometry") if value.get("type") == "Feature" else value
        return shape(candidate) if candidate else GeometryCollection()
    except (TypeError, ValueError):
        return GeometryCollection()


def _layer_union(layer: AgricultureAnalysisLayer | None):
    if layer is None:
        return GeometryCollection()
    geometries = [_geometry(feature.get("geometry")) for feature in (layer.geojson or {}).get("features", [])]
    return unary_union([geometry for geometry in geometries if not geometry.is_empty]) if geometries else GeometryCollection()


def alignment_metrics(current_layer: AgricultureAnalysisLayer | None, reference_layer: AgricultureAnalysisLayer | None) -> dict[str, Any]:
    current = _layer_union(current_layer)
    reference = _layer_union(reference_layer)
    if current.is_empty or reference.is_empty:
        return {"status": "failed", "method": "quality_footprints", "alignment_score": 0.0, "overlap_pct": 0.0, "failure_reasons": ["missing_quality_footprints"], "transform": {}}
    intersection = current.intersection(reference).area
    union = current.union(reference).area
    overlap = intersection / union if union else 0.0
    return {"status": "aligned" if overlap >= 0.35 else "low_confidence", "method": "quality_footprints_identity_transform", "alignment_score": float(overlap), "overlap_pct": float(overlap * 100), "failure_reasons": [] if overlap >= 0.35 else ["insufficient_spatial_overlap"], "transform": {"type": "identity", "crs": "EPSG:4326"}, "metrics": {"current_area_m2_approx": float(current.area), "reference_area_m2_approx": float(reference.area)}}


def _comparison_state(current: AgricultureObservation, previous: AgricultureObservation | None, intersection_ratio: float) -> tuple[str, float | None, float | None, float]:
    if previous is None:
        return "new", current.area_m2, current.area_m2, float(current.confidence * 0.8)
    delta_area = (current.area_m2 - previous.area_m2) if current.area_m2 is not None and previous.area_m2 is not None else None
    delta_intensity = float(current.severity - previous.severity)
    area_ratio = (delta_area / max(abs(previous.area_m2), 1.0)) if delta_area is not None else 0.0
    if intersection_ratio < 0.05:
        return "new", current.area_m2, delta_area, float(min(current.confidence, previous.confidence) * 0.75)
    if area_ratio > 0.2 or delta_intensity > 0.15:
        state = "expanding"
    elif area_ratio < -0.2 or delta_intensity < -0.15:
        state = "improving"
    else:
        state = "stable"
    return state, current.area_m2, delta_area, float(min(current.confidence, previous.confidence) * max(0.0, intersection_ratio))


def build_changes(current: Iterable[AgricultureObservation], previous: Iterable[AgricultureObservation], *, current_flight_id: str, reference_flight_id: str, field_id: int) -> list[dict[str, Any]]:
    current_rows = [row for row in current if row.review_state != "rejected" and not getattr(row, "merged_into_id", None)]
    previous_rows = [row for row in previous if row.review_state != "rejected" and not getattr(row, "merged_into_id", None)]
    matched_previous: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in sorted(current_rows, key=lambda item: (item.observation_type, item.id)):
        current_geometry = _geometry(row.geometry_geojson)
        candidates = [candidate for candidate in previous_rows if candidate.id not in matched_previous and candidate.observation_type == row.observation_type]
        best: tuple[float, AgricultureObservation | None] = (0.0, None)
        for candidate in candidates:
            previous_geometry = _geometry(candidate.geometry_geojson)
            if current_geometry.is_empty or previous_geometry.is_empty:
                ratio = 0.0
            else:
                union_area = current_geometry.union(previous_geometry).area
                ratio = current_geometry.intersection(previous_geometry).area / union_area if union_area else 0.0
            if ratio > best[0]: best = (ratio, candidate)
        matched = best[1] if best[0] >= 0.05 else None
        state, area, delta_area, confidence = _comparison_state(row, matched, best[0])
        if matched is not None: matched_previous.add(matched.id)
        evidence = [*row.evidence_ids, *(matched.evidence_ids if matched else [])]
        output.append({"id": stable_temporal_id(current_flight_id, reference_flight_id, row.id, matched.id if matched else "new"), "field_id": field_id, "current_flight_id": current_flight_id, "reference_flight_id": reference_flight_id, "current_observation_id": row.id, "previous_observation_id": matched.id if matched else None, "observation_type": row.observation_type, "state": state, "geometry_geojson": row.geometry_geojson, "reference_geometry_geojson": matched.geometry_geojson if matched else {}, "area_m2": area, "delta_area_m2": delta_area, "delta_intensity": float(row.severity - matched.severity) if matched else None, "confidence": confidence, "evidence_ids": evidence, "uncertainty": {"intersection_ratio": best[0], "excluded_rejected": True, "comparison_policy": "same_type_geometric_overlap", "minimum_match_overlap": 0.05}})
    for row in previous_rows:
        if row.id in matched_previous: continue
        output.append({"id": stable_temporal_id(current_flight_id, reference_flight_id, "resolved", row.id), "field_id": field_id, "current_flight_id": current_flight_id, "reference_flight_id": reference_flight_id, "current_observation_id": None, "previous_observation_id": row.id, "observation_type": row.observation_type, "state": "resolved", "geometry_geojson": {}, "reference_geometry_geojson": row.geometry_geojson, "area_m2": None, "delta_area_m2": -(row.area_m2 or 0.0), "delta_intensity": -row.severity, "confidence": float(row.confidence * 0.7), "evidence_ids": list(row.evidence_ids), "uncertainty": {"intersection_ratio": 0.0, "excluded_rejected": True, "comparison_policy": "unmatched_previous_observation"}})
    return output


def summarize_changes(changes: Iterable[Any]) -> dict[str, float | int]:
    rows = list(changes)
    value = lambda row, key, default=None: row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)
    summary: dict[str, float | int] = {
        state: sum(value(row, "state") == state for row in rows)
        for state in ("new", "expanding", "stable", "improving", "resolved")
    }
    summary["persistent"] = sum(value(row, "state") in {"expanding", "stable", "improving"} for row in rows)
    summary["count_change"] = int(summary["new"]) - int(summary["resolved"])
    summary["area_change_m2"] = float(sum(float(value(row, "delta_area_m2", 0) or 0) for row in rows))
    summary["current_area_m2"] = float(sum(float(value(row, "area_m2", 0) or 0) for row in rows))
    summary["reference_area_m2"] = max(0.0, float(summary["current_area_m2"]) - float(summary["area_change_m2"]))
    return summary


class AgricultureTemporalService:
    async def select_reference_flight(self, db: AsyncSession, *, current: AgricultureFlight, override_flight_id: str | None = None, min_quality_score: float = 0.6) -> AgricultureFlight | None:
        if override_flight_id:
            candidate = await agriculture_repository.get_flight(db, flight_id=override_flight_id)
            if candidate and candidate.field_id == current.field_id and candidate.id != current.id:
                return candidate
            return None
        flights = await agriculture_repository.list_flights(db, field_id=current.field_id, user=type("User", (), {"org_id": current.org_id})(), limit=100)
        eligible = []
        for flight in flights:
            if flight.id == current.id or flight.created_at >= current.created_at or flight.status not in {"review", "published", "archived", "captured"}: continue
            quality = flight.quality_summary or {}
            if quality.get("status") not in {"pass", "warning"} or float(quality.get("score", 0.0)) < min_quality_score: continue
            current_profile = current.profile_snapshot or {}; candidate_profile = flight.profile_snapshot or {}
            if current_profile.get("crop_type") and candidate_profile.get("crop_type") != current_profile.get("crop_type"): continue
            if current_profile.get("growth_stage") and candidate_profile.get("growth_stage") != current_profile.get("growth_stage"): continue
            if current_profile.get("sensor_inventory") and candidate_profile.get("sensor_inventory") != current_profile.get("sensor_inventory"): continue
            eligible.append(flight)
        return max(eligible, key=lambda item: item.created_at, default=None)

    async def list_comparable_flights(
        self,
        db: AsyncSession,
        *,
        current: AgricultureFlight,
        min_quality_score: float = 0.6,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        flights = await agriculture_repository.list_flights(
            db,
            field_id=current.field_id,
            user=type("User", (), {"org_id": current.org_id})(),
            limit=100,
        )
        current_run = await self._latest_run(db, current.id)
        current_layer = None
        if current_run is not None:
            current_layer = await db.scalar(
                select(AgricultureAnalysisLayer).where(
                    AgricultureAnalysisLayer.run_id == current_run.id,
                    AgricultureAnalysisLayer.layer_name == "quality",
                )
            )
        candidates: list[dict[str, Any]] = []
        for flight in flights:
            if flight.id == current.id:
                continue
            reference_run = await self._latest_run(db, flight.id)
            reference_layer = None
            if reference_run is not None:
                reference_layer = await db.scalar(
                    select(AgricultureAnalysisLayer).where(
                        AgricultureAnalysisLayer.run_id == reference_run.id,
                        AgricultureAnalysisLayer.layer_name == "quality",
                    )
                )
            alignment = alignment_metrics(current_layer, reference_layer)
            comparability = score_comparability(
                current=current,
                reference=flight,
                current_run=current_run,
                reference_run=reference_run,
                alignment=alignment,
                min_quality_score=min_quality_score,
            )
            candidates.append(
                {
                    "flight_id": flight.id,
                    "created_at": flight.created_at.isoformat() if flight.created_at else None,
                    "status": flight.status,
                    "comparability": comparability,
                    "alignment": alignment,
                }
            )
        candidates.sort(
            key=lambda item: (
                0 if item["comparability"]["eligible"] else 1,
                -float(item["comparability"]["score"]),
                str(item["flight_id"]),
            )
        )
        return candidates[: max(1, limit)]

    async def compare(self, db: AsyncSession, *, current: AgricultureFlight, reference_flight_id: str | None = None, min_quality_score: float = 0.6) -> dict[str, Any]:
        reference = await self.select_reference_flight(db, current=current, override_flight_id=reference_flight_id, min_quality_score=min_quality_score)
        if reference is None:
            raise ValueError("No comparable quality-approved reference flight found")
        current_run = await self._latest_run(db, current.id); reference_run = await self._latest_run(db, reference.id)
        if current_run is None or reference_run is None:
            raise ValueError("Both flights require completed agriculture analysis runs")
        current_layer = await db.scalar(select(AgricultureAnalysisLayer).where(AgricultureAnalysisLayer.run_id == current_run.id, AgricultureAnalysisLayer.layer_name == "quality"))
        reference_layer = await db.scalar(select(AgricultureAnalysisLayer).where(AgricultureAnalysisLayer.run_id == reference_run.id, AgricultureAnalysisLayer.layer_name == "quality"))
        alignment = alignment_metrics(current_layer, reference_layer)
        alignment["metrics"] = {
            **dict(alignment.get("metrics") or {}),
            "current_run_id": current_run.id,
            "reference_run_id": reference_run.id,
            "methodology_version": "observation_change.v1",
            "matching_policy": "same_type_geometric_overlap",
            "alignment_status": alignment.get("status"),
        }
        comparability = score_comparability(
            current=current,
            reference=reference,
            current_run=current_run,
            reference_run=reference_run,
            alignment=alignment,
            min_quality_score=min_quality_score,
        )
        comparison_status = (
            "failed"
            if alignment.get("status") == "failed"
            else "incompatible"
            if not comparability.get("eligible")
            else "completed"
        )
        alignment["metrics"]["comparison_status"] = comparison_status
        alignment_row = await db.scalar(select(AgricultureFlightAlignment).where(AgricultureFlightAlignment.current_flight_id == current.id, AgricultureFlightAlignment.reference_flight_id == reference.id))
        if alignment_row is None:
            alignment_row = AgricultureFlightAlignment(field_id=current.field_id, current_flight_id=current.id, reference_flight_id=reference.id)
            db.add(alignment_row)
        for key, value in alignment.items():
            setattr(alignment_row, key, value)
        alignment_row.comparability = comparability
        if alignment.get("status") == "failed" or not comparability.get("eligible"):
            # Never silently emit deltas for incompatible model/sensor/calibration inputs.
            await db.execute(
                delete(AgricultureObservationChange).where(
                    AgricultureObservationChange.current_flight_id == current.id,
                    AgricultureObservationChange.reference_flight_id == reference.id,
                )
            )
            await db.commit()
            return {
                "status": comparison_status,
                "current_flight_id": current.id,
                "reference_flight_id": reference.id,
                "alignment": alignment,
                "comparability": comparability,
                "changes": [],
                "summary": {},
                "source_runs": {"current": current_run.id, "reference": reference_run.id},
                "methodology": {
                    "version": "observation_change.v1",
                    "alignment": alignment.get("method"),
                    "matching": "same_type_geometric_overlap",
                },
            }
        current_rows = list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.run_id == current_run.id))).all())
        previous_rows = list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.run_id == reference_run.id))).all())
        payloads = build_changes(current_rows, previous_rows, current_flight_id=current.id, reference_flight_id=reference.id, field_id=current.field_id)
        for payload in payloads:
            uncertainty = dict(payload.get("uncertainty") or {})
            uncertainty["comparability_warnings"] = list(comparability.get("warnings") or [])
            uncertainty["comparability_score"] = comparability.get("score")
            payload["uncertainty"] = uncertainty
        await db.execute(delete(AgricultureObservationChange).where(AgricultureObservationChange.current_flight_id == current.id, AgricultureObservationChange.reference_flight_id == reference.id))
        db.add_all(AgricultureObservationChange(**payload) for payload in payloads)
        await db.commit()
        return {
            "status": comparison_status,
            "current_flight_id": current.id,
            "reference_flight_id": reference.id,
            "alignment": alignment,
            "comparability": comparability,
            "changes": payloads,
            "summary": summarize_changes(payloads),
            "source_runs": {"current": current_run.id, "reference": reference_run.id},
            "methodology": {
                "version": "observation_change.v1",
                "alignment": alignment.get("method"),
                "matching": "same_type_geometric_overlap",
            },
        }

    async def _latest_run(self, db: AsyncSession, flight_id: str) -> AgricultureAnalysisRun | None:
        return await db.scalar(select(AgricultureAnalysisRun).where(AgricultureAnalysisRun.flight_id == flight_id, AgricultureAnalysisRun.status.in_(["review", "completed", "published"])).order_by(AgricultureAnalysisRun.created_at.desc()).limit(1))


agriculture_temporal_service = AgricultureTemporalService()
