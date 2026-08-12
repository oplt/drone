from __future__ import annotations

import hashlib
import json
import math
from time import perf_counter
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from pathlib import Path

from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon, shape
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import Session
from backend.core.config.runtime import settings
from backend.modules.agriculture.models import (
    AgricultureAnalysisRun,
    AgricultureAnalysisLayer,
    AgricultureAnalysisStage,
    AgricultureAnalysisVideoJob,
    AgricultureCameraCalibration,
    AgricultureFieldProfile,
    AgricultureFlight,
    AgricultureFrameLineage,
    AgricultureFrameQuality,
    AgricultureHealthBaseline,
    AgricultureMediaManifest,
    AgricultureObservation,
    AgricultureObservationEvidence,
    AgricultureTelemetrySample,
)
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.events import emit_agriculture_event
from backend.modules.agriculture.aggregation import aggregate_detections
from backend.modules.agriculture.policy import agriculture_validator
from backend.modules.agriculture.quality import aggregate_quality, analysis_suitability, compute_frame_quality, telemetry_quality_summary
from backend.modules.agriculture.heuristics import infer_row_structure, segment_rgb_crop_soil_water
from backend.modules.agriculture.heuristics import anomaly_signature
from backend.modules.agriculture.stand import summarize_stands
from backend.modules.agriculture.rgb_products import evaluate_rgb_products, product_gate_summary
from backend.modules.agriculture.contracts import irrigation_zone_to_observation
from backend.modules.agriculture.analysis_orchestration import (
    agriculture_analysis_orchestration,
)
from backend.modules.agriculture.schemas import (
    AgricultureMissionProfile,
    CalibrationIn,
    FieldProfilePatch,
    FrameManifestIn,
    PlanPreviewRequest,
    TelemetryBatchIn,
)
from backend.modules.agriculture.storage import agriculture_storage
from backend.modules.fields.models import Field
from backend.modules.video_analysis.contracts import (
    VideoSourceRef,
    video_analysis_port,
)
from backend.modules.irrigation.models import AnomalyZone
from backend.infrastructure.runtime.blocking import run_blocking


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def stable_record_id(*parts: object) -> str:
    """Stable UUID-compatible key for rerunnable derived records."""
    value = "|".join(str(part) for part in parts)
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def geometry_4326(value: dict[str, Any]) -> Any | None:
    """Convert external GeoJSON to canonical PostGIS geometry without changing SRID."""
    if not value:
        return None
    geometry = shape(value)
    if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Canonical agriculture geometry must be Polygon or MultiPolygon")
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Canonical agriculture geometry is invalid")
    return from_shape(geometry, srid=4326)


def polygon_area_m2(coords: list[list[float]]) -> float:
    points = [(float(p[0]), float(p[1])) for p in coords]
    if points[0] != points[-1]:
        points.append(points[0])
    if len(points) < 4:
        raise ValueError("field polygon requires at least three points")
    poly = Polygon(points)
    if not poly.is_valid or poly.area <= 0:
        raise ValueError("field polygon invalid or zero-area")
    lat0 = sum(point[1] for point in points[:-1]) / (len(points) - 1)
    meters_per_lon = 111_320 * max(0.1, math.cos(math.radians(lat0)))
    meters_per_lat = 110_574
    return float(poly.area * meters_per_lon * meters_per_lat)


class AgricultureService:
    @staticmethod
    def _rgb_model_evidence(model_snapshots: dict[str, Any]) -> dict[str, Any]:
        """Build product evidence only from releases frozen onto this run."""
        product_names = {
            "object_detection": ("object_detection",),
            "stand_count": ("stand_count",),
            "weed_detection": ("weed_detection",),
            "crop_health": ("crop_health",),
            "canopy_cover": ("canopy_cover",),
            "row_detection": ("row_detection",),
            "standing_water": ("standing_water",),
        }
        evidence: dict[str, Any] = {}
        for capability_id, snapshot_value in model_snapshots.items():
            snapshot = dict(snapshot_value or {})
            item = {
                "capability_id": capability_id,
                "release_id": snapshot.get("release_id"),
                "model_id": snapshot.get("model_id"),
                "model_version_id": snapshot.get("vision_model_version_id"),
                "version": snapshot.get("model_version"),
                "artifact_digest": snapshot.get("model_checksum"),
                "validated": snapshot.get("status") == "active",
                "inference_profile": snapshot.get("inference_profile") or {},
            }
            for product_name in product_names.get(capability_id, (capability_id,)):
                evidence[product_name] = item
        return evidence
    def validate_profile(self, *, profile: AgricultureMissionProfile, cruise_alt_m: float, field_polygon_lonlat: list[list[float]], route_lonlat: list[list[float]] | None = None) -> None:
        result = agriculture_validator.validate(
            profile=profile,
            cruise_alt_m=cruise_alt_m,
            field_polygon_lonlat=field_polygon_lonlat,
            route_lonlat=route_lonlat,
        )
        if not result.valid:
            raise ValueError("Agriculture profile invalid: " + ", ".join(result.errors))

    async def get_or_create_profile(self, db: AsyncSession, *, field_id: int, user) -> AgricultureFieldProfile:
        profile = await agriculture_repository.get_profile(db, field_id=field_id, user=user)
        if profile is not None:
            return profile
        field = await db.scalar(select(Field).where(Field.id == field_id))
        if field is None:
            raise ValueError("Field not found")
        if user.org_id is not None and field.org_id != user.org_id:
            raise ValueError("Field not found")
        profile = AgricultureFieldProfile(field_id=field_id, org_id=field.org_id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        return profile

    async def patch_profile(self, db: AsyncSession, *, field_id: int, user, patch: FieldProfilePatch) -> AgricultureFieldProfile:
        profile = await self.get_or_create_profile(db, field_id=field_id, user=user)
        values = patch.model_dump(mode="json", exclude_unset=True)
        if "metadata" in values:
            values["metadata_json"] = values.pop("metadata")
        if "planting_date" in values and values["planting_date"] is not None:
            values["planting_date"] = str(values["planting_date"])
        for key, value in values.items():
            setattr(profile, key, value)
        await db.commit()
        await db.refresh(profile)
        return profile

    async def preview(self, request: PlanPreviewRequest) -> dict[str, Any]:
        self.validate_profile(
            profile=request.profile,
            cruise_alt_m=request.cruise_alt_m,
            field_polygon_lonlat=request.field_polygon_lonlat,
        )
        area = polygon_area_m2(request.field_polygon_lonlat)
        profile = request.profile
        footprint_w = 2 * request.cruise_alt_m * math.tan(math.radians(profile.fov_h_deg / 2))
        footprint_h = 2 * request.cruise_alt_m * math.tan(math.radians(profile.fov_v_deg / 2))
        gsd = max(footprint_w / 4000, footprint_h / 3000) * 100
        warnings: list[str] = []
        if gsd > profile.target_gsd_cm:
            warnings.append("planned_gsd_exceeds_target")
        if profile.camera_orientation != "nadir":
            warnings.append("oblique_camera_footprint_requires_calibration")
        route_length = request.route_length_m
        duration = route_length / max(profile.speed_mps, 0.1) if route_length else None
        image_count = int(math.ceil(route_length / max(0.5, footprint_h * (1 - profile.front_overlap_pct / 100)))) if route_length else None
        return {"field_id": request.field_id, "area_m2": area, "area_ha": area / 10_000, "footprint_width_m": footprint_w, "footprint_height_m": footprint_h, "estimated_gsd_cm": gsd, "coverage_pct": 100.0, "estimated_duration_s": duration, "estimated_image_count": image_count, "warnings": warnings}

    async def ensure_flight_for_mission(self, *, mission_id: str, field_id: int, org_id: int | None, profile: dict[str, Any], season: str | None, flight_kind: str = "agriculture_survey", profile_snapshot_hash: str | None = None, status: str = "planned") -> AgricultureFlight:
        async with Session() as db:
            existing = await agriculture_repository.get_flight_by_mission(db, mission_id=mission_id)
            if existing is not None:
                return existing
            field = await db.scalar(select(Field).where(Field.id == field_id))
            if field is None or (org_id is not None and field.org_id != org_id):
                raise ValueError("Agriculture field not found")
            if flight_kind != "agriculture_survey":
                raise ValueError("Unsupported agriculture flight kind")
            if status not in {"planned", "preflight", "running"}:
                raise ValueError("Invalid agriculture flight start status")
            flight = AgricultureFlight(id=mission_id, mission_id=mission_id, field_id=field_id, org_id=org_id, season=season, flight_kind=flight_kind, status=status, profile_snapshot=profile, profile_snapshot_version=int(profile.get("snapshot_version", 1)), profile_snapshot_hash=profile_snapshot_hash, started_at=datetime.now(UTC) if status == "running" else None)
            db.add(flight)
            await db.commit()
            await db.refresh(flight)
            return flight

    async def transition_flight(self, db: AsyncSession, *, flight: AgricultureFlight, target: str) -> AgricultureFlight:
        allowed = {
            "planned": {"preflight", "cancelled", "failed"},
            "preflight": {"running", "cancelled", "failed"},
            "running": {"captured", "cancelled", "failed"},
            "captured": {"processing", "archived"},
            "processing": {"review", "failed", "cancelled"},
            "review": {"processing", "published", "archived"},
            "published": {"archived"},
            "failed": {"processing", "archived"},
            "cancelled": {"archived"},
            "archived": set(),
        }
        if target == flight.status:
            return flight
        if target not in allowed.get(flight.status, set()):
            raise ValueError(f"Invalid agriculture flight transition: {flight.status} -> {target}")
        flight.status = target
        now = datetime.now(UTC)
        if target == "running" and flight.started_at is None:
            flight.started_at = now
        if target in {"captured", "failed", "cancelled", "archived", "published"} and flight.ended_at is None:
            flight.ended_at = now
        await db.flush()
        return flight

    async def reconcile_mission_terminal_state(self, *, mission_id: str, mission_state: str) -> None:
        target = {"completed": "captured", "failed": "failed", "aborted": "cancelled"}.get(mission_state)
        if target is None:
            return
        async with Session() as db:
            flight = await agriculture_repository.get_flight_by_mission(db, mission_id=mission_id)
            if flight is None or flight.status in {"captured", "processing", "review", "published", "archived", "failed", "cancelled"}:
                return
            await self.transition_flight(db, flight=flight, target=target)
            await db.commit()

    async def ingest_telemetry(self, db: AsyncSession, *, flight: AgricultureFlight, batch: TelemetryBatchIn) -> tuple[int, int, int, int]:
        existing = await agriculture_repository.list_telemetry(db, flight_id=flight.id)
        keys = {(row.timestamp_utc, row.source) for row in existing}
        inserted = duplicates = rejected = 0
        rows = []
        for sample in batch.samples:
            timestamp = utc(sample.timestamp) + timedelta(seconds=batch.clock_offset_seconds)
            if not math.isfinite(sample.lat) or not math.isfinite(sample.lon):
                rejected += 1
                continue
            key = (timestamp, sample.source)
            if key in keys:
                duplicates += 1
                continue
            keys.add(key)
            rows.append(AgricultureTelemetrySample(flight_id=flight.id, timestamp_utc=timestamp, lat=sample.lat, lon=sample.lon, relative_altitude_m=sample.relative_altitude_m, absolute_altitude_m=sample.absolute_altitude_m, roll_deg=sample.roll_deg, pitch_deg=sample.pitch_deg, yaw_deg=sample.yaw_deg, gimbal_roll_deg=sample.gimbal_roll_deg, gimbal_pitch_deg=sample.gimbal_pitch_deg, gimbal_yaw_deg=sample.gimbal_yaw_deg, ground_speed_mps=sample.ground_speed_mps, gps_quality=sample.gps_quality, camera_trigger=sample.camera_trigger, source=sample.source, source_key=sample.source_key, raw=sample.raw))
        db.add_all(rows)
        await db.flush()
        inserted = len(rows)
        all_rows = sorted(existing + rows, key=lambda row: row.timestamp_utc)
        gaps = sum(1 for a, b in zip(all_rows, all_rows[1:]) if (b.timestamp_utc - a.timestamp_utc).total_seconds() > 5)
        if gaps:
            emit_agriculture_event("telemetry_gap", flight_id=flight.id, gap_count=gaps)
            from backend.observability import prometheus_metrics
            prometheus_metrics.agriculture_telemetry_gaps_total.labels(source="ingest").inc(gaps)
        emit_agriculture_event(
            "ingest_completed", flight_id=flight.id, kind="telemetry",
            inserted=inserted, duplicates=duplicates, rejected=rejected, gap_count=gaps,
        )
        return inserted, duplicates, rejected, gaps

    async def register_media(self, db: AsyncSession, *, flight: AgricultureFlight, values: dict[str, Any]) -> AgricultureMediaManifest:
        agriculture_storage.validate_tenant_key(str(values["storage_key"]), org_id=flight.org_id, resource=f"flights/{flight.id}")
        agriculture_storage.validate_content(content_type=values.get("content_type"), byte_size=values.get("byte_size"), quota_bytes=settings.agriculture_max_media_bytes)
        values = {
            **values,
            "storage_class": values.get("storage_class", "standard"),
            "artifact_version": int(values.get("artifact_version", 1)),
            "retention_expires_at": values.get("retention_expires_at") or datetime.now(UTC) + timedelta(days=max(1, settings.agriculture_media_retention_days)),
        }
        existing = await db.scalar(select(AgricultureMediaManifest).where(
            AgricultureMediaManifest.flight_id == flight.id,
            AgricultureMediaManifest.checksum == values["checksum"],
            AgricultureMediaManifest.source_kind == values["source_kind"],
        ))
        if existing is not None:
            return existing
        manifest = AgricultureMediaManifest(flight_id=flight.id, **values)
        db.add(manifest)
        await db.commit()
        await db.refresh(manifest)
        emit_agriculture_event("ingest_completed", flight_id=flight.id, kind="media", media_id=manifest.id)
        return manifest

    async def register_calibration(self, db: AsyncSession, *, user, payload: CalibrationIn) -> AgricultureCameraCalibration:
        existing = await db.get(AgricultureCameraCalibration, payload.id)
        if existing is not None:
            if existing.org_id != user.org_id:
                raise ValueError("Calibration not found")
            return existing
        calibration = AgricultureCameraCalibration(
            id=payload.id,
            org_id=user.org_id,
            camera_serial=payload.camera_serial,
            calibration_type=payload.calibration_type,
            intrinsics_json=payload.intrinsics,
            distortion_json=payload.distortion,
            extrinsics_json=payload.extrinsics,
            valid_from=payload.valid_from,
            checksum=payload.checksum,
        )
        db.add(calibration)
        await db.commit()
        await db.refresh(calibration)
        return calibration

    async def create_frame_manifest(self, db: AsyncSession, *, flight: AgricultureFlight, payload: FrameManifestIn) -> dict[str, Any]:
        media = await db.scalar(select(AgricultureMediaManifest).where(
            AgricultureMediaManifest.id == payload.media_id,
            AgricultureMediaManifest.flight_id == flight.id,
        ))
        if media is None:
            raise ValueError("Media manifest not found for flight")
        if payload.source_checksum != media.checksum:
            raise ValueError("Frame manifest checksum does not match its canonical media asset")
        telemetry_ids = {
            sample_id
            for frame in payload.frames
            for sample_id in (frame.telemetry_sample_before_id, frame.telemetry_sample_after_id)
            if sample_id is not None
        }
        if telemetry_ids:
            owned_ids = set((await db.scalars(select(AgricultureTelemetrySample.id).where(
                AgricultureTelemetrySample.flight_id == flight.id,
                AgricultureTelemetrySample.id.in_(telemetry_ids),
            ))).all())
            if owned_ids != telemetry_ids:
                raise ValueError("Frame pose references telemetry outside this flight")
        telemetry_checksum = payload.telemetry_checksum or "none"
        config_blob = json.dumps(payload.sampling_config, sort_keys=True, separators=(",", ":"))
        manifest_checksum = hashlib.sha256(f"{payload.source_checksum}:{telemetry_checksum}:{config_blob}".encode()).hexdigest()
        existing = list((await db.scalars(select(AgricultureFrameLineage).where(AgricultureFrameLineage.media_id == media.id))).all())
        if not existing:
            db.add_all([
                AgricultureFrameLineage(
                    flight_id=flight.id,
                    media_id=media.id,
                    frame_index=frame.frame_index,
                    timestamp_utc=utc(frame.timestamp),
                    image_width=frame.image_width,
                    image_height=frame.image_height,
                    source_checksum=payload.source_checksum,
                    sampling_config=payload.sampling_config,
                    pose_interpolation_status=frame.pose_interpolation_status,
                    telemetry_sample_before_id=frame.telemetry_sample_before_id,
                    telemetry_sample_after_id=frame.telemetry_sample_after_id,
                    footprint_geojson=frame.footprint_geojson,
                    footprint=geometry_4326(frame.footprint_geojson),
                    gsd_cm=frame.gsd_cm,
                    quality_metrics=frame.quality_metrics,
                    evidence_artifact_ids=frame.evidence_artifact_ids,
                ) for frame in payload.frames
            ])
            await db.commit()
        flight.input_manifest = {
            **(flight.input_manifest or {}),
            "frame_manifest_checksum": manifest_checksum,
            "source_checksum": payload.source_checksum,
            "telemetry_checksum": telemetry_checksum,
            "sampling_config": payload.sampling_config,
            "frame_count": len(payload.frames),
        }
        await db.commit()
        return {"media_id": media.id, "frame_count": len(payload.frames), "manifest_checksum": manifest_checksum}

    async def create_analysis_run(self, db: AsyncSession, *, flight: AgricultureFlight, values: dict[str, Any]) -> AgricultureAnalysisRun:
        manifest = json.dumps({
            "input_manifest": flight.input_manifest or {},
            "analysis_profile": values.get("analysis_profile"),
            "requested_analyses": values.get("requested_analyses", []),
            "parameters": values.get("parameters", {}),
            "model_versions": values.get("model_versions", {}),
            "calibration_versions": values.get("calibration_versions", {}),
            "baseline_flight_id": values.get("baseline_flight_id"),
        }, sort_keys=True, separators=(",", ":"))
        input_checksum = hashlib.sha256(manifest.encode()).hexdigest()
        existing = await agriculture_repository.get_run_by_key(db, flight_id=flight.id, key=values["idempotency_key"])
        if existing is not None:
            if existing.input_checksum != input_checksum:
                raise ValueError("Idempotency key was already used with different analysis inputs")
            return existing
        input_manifest = json.loads(manifest)
        baseline_flight_id = values.get("baseline_flight_id")
        if baseline_flight_id:
            baseline = await db.get(AgricultureFlight, baseline_flight_id)
            if baseline is None or baseline.field_id != flight.field_id or baseline.org_id != flight.org_id:
                raise ValueError("Baseline flight must belong to the same field and organization")
        run = AgricultureAnalysisRun(
            flight_id=flight.id,
            input_manifest=input_manifest,
            input_checksum=input_checksum,
            audit_json={"created_at": datetime.now(UTC).isoformat(), "event": "analysis_requested"},
            **values,
        )
        db.add(run)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await agriculture_repository.get_run_by_key(db, flight_id=flight.id, key=values["idempotency_key"])
            if existing is not None:
                if existing.input_checksum != input_checksum:
                    raise ValueError("Idempotency key was already used with different analysis inputs")
                return existing
            raise
        await db.refresh(run)
        emit_agriculture_event("analysis_started", flight_id=flight.id, analysis_run_id=run.id)
        return run

    async def process_analysis_run(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, force: bool = False, cluster_radius_m: float = 8.0) -> AgricultureAnalysisRun:
        if run.status in {"cancelled", "review", "published", "completed"} and not force:
            return run
        prerequisite, linked_job_ids = (
            await agriculture_analysis_orchestration.prerequisite_state(
                db, run=run, flight=flight
            )
        )
        if prerequisite != "completed":
            return run
        if flight.status == "captured":
            await self.transition_flight(db, flight=flight, target="processing")
        stage = await db.scalar(select(AgricultureAnalysisStage).where(AgricultureAnalysisStage.run_id == run.id, AgricultureAnalysisStage.stage_name == "quality"))
        if stage is None:
            stage = AgricultureAnalysisStage(run_id=run.id, stage_name="quality")
            db.add(stage)
        stage.status = "running"; stage.attempt += 1; stage.started_at = datetime.now(UTC); stage.error = None
        run.status = "running"; run.progress = 5.0
        await db.commit()
        try:
            videos = await video_analysis_port.list_mission_sources(
                db,
                mission_id=flight.mission_id,
                org_id=flight.org_id,
                user_id=run.requested_by_user_id,
            )
            telemetry_rows = await agriculture_repository.list_telemetry(db, flight_id=flight.id)
            quality_rows, quality_summary, vision_summary = await run_blocking(self._sample_video_quality, videos, run.id, flight.id, boundary="media", operation="agriculture_quality", timeout_s=300.0)
            telemetry_summary = telemetry_quality_summary(telemetry_rows)
            profile_snapshot = flight.profile_snapshot or {}
            gsd_values = list((await db.scalars(select(AgricultureFrameLineage.gsd_cm).where(AgricultureFrameLineage.flight_id == flight.id, AgricultureFrameLineage.gsd_cm.is_not(None)))).all())
            estimated_gsd = min((float(value) for value in gsd_values), default=None)
            suitability = analysis_suitability(estimated_gsd_cm=estimated_gsd, target_gsd_cm=float(profile_snapshot.get("target_gsd_cm", 2.0)), requested_analyses=run.requested_analyses or [])
            quality_summary = {**quality_summary, "telemetry": telemetry_summary, "video_count": len(videos), "suitability": suitability, "vision_fallback": vision_summary}
            if suitability.get("status") == "blocked": quality_summary["status"] = "blocked"
            await db.execute(delete(AgricultureFrameQuality).where(AgricultureFrameQuality.run_id == run.id))
            db.add_all(quality_rows)
            lineage_rows = list((await db.scalars(select(AgricultureFrameLineage).where(AgricultureFrameLineage.flight_id == flight.id))).all())
            lineage_by_frame = {row.frame_index: row for row in lineage_rows}
            quality_features = []
            for quality_row in quality_rows:
                lineage = lineage_by_frame.get(quality_row.frame_index)
                if lineage is None or not lineage.footprint_geojson:
                    continue
                footprint = lineage.footprint_geojson
                geometry = footprint.get("geometry") if footprint.get("type") == "Feature" else footprint if footprint.get("type") in {"Point", "Polygon", "MultiPolygon"} else None
                if geometry is None:
                    continue
                quality_features.append({"type": "Feature", "id": quality_row.id, "geometry": geometry, "properties": {"score": quality_row.score, "state": quality_row.state, "frame_index": quality_row.frame_index, "reasons": quality_row.metrics.get("reasons", [])}})
            quality_summary["spatial_quality_frame_count"] = len(quality_features)
            quality_summary["reflight_frame_count"] = sum(row.state == "blocked" for row in quality_rows)
            stage.metrics = quality_summary; stage.output_checksum = hashlib.sha256(json.dumps(quality_summary, sort_keys=True, default=str).encode()).hexdigest()
            stage.status = "completed"; stage.progress = 100.0; stage.finished_at = datetime.now(UTC)
            run.quality_gate = quality_summary
            run.progress = 35.0
            await db.commit()
            emit_agriculture_event("quality_completed", flight_id=flight.id, analysis_run_id=run.id, status=quality_summary.get("status"), score=quality_summary.get("score"))

            if quality_summary.get("status") == "blocked":
                run.status = "blocked_quality"
                run.error = "Image-quality gate blocked agricultural inference"
                flight.quality_summary = quality_summary
                if flight.status == "processing":
                    await self.transition_flight(db, flight=flight, target="review")
                await db.commit()
                return run

            if run.status == "cancelled":
                return run
            inference_stage = await db.scalar(select(AgricultureAnalysisStage).where(AgricultureAnalysisStage.run_id == run.id, AgricultureAnalysisStage.stage_name == "observation_aggregation"))
            if inference_stage is None:
                inference_stage = AgricultureAnalysisStage(run_id=run.id, stage_name="observation_aggregation")
                db.add(inference_stage)
            inference_stage.status = "running"; inference_stage.attempt += 1; inference_stage.started_at = datetime.now(UTC)
            stage = inference_stage
            inference_started = perf_counter()
            detections = await video_analysis_port.list_detections(
                db, job_ids=linked_job_ids, org_id=flight.org_id
            )
            inference_links = list(
                (
                    await db.scalars(
                        select(AgricultureAnalysisVideoJob).where(
                            AgricultureAnalysisVideoJob.run_id == run.id
                        )
                    )
                ).all()
            )
            inference_by_job = {
                link.video_job_id: link for link in inference_links
            }
            requested_rgb = list(run.requested_analyses or [])
            rgb_products = evaluate_rgb_products(
                segmentation=vision_summary,
                row={"confidence": vision_summary.get("row_direction_confidence")},
                quality=quality_summary,
                detections=detections,
                requested=requested_rgb,
            )
            rgb_gates = product_gate_summary(
                rgb_products,
                evaluated_models=self._rgb_model_evidence(run.model_versions or {}),
            )
            run.quality_gate = {**(run.quality_gate or {}), "rgb_products": rgb_gates, "claim_policy": "RGB products remain candidate-only until model evaluation and human review pass."}
            observation_payloads = aggregate_detections(detections, cluster_radius_m=cluster_radius_m)
            irrigation_zones = list((await db.scalars(select(AnomalyZone).where(AnomalyZone.mission_id == flight.mission_id).order_by(AnomalyZone.id.asc()))).all())
            observation_payloads.extend(irrigation_zone_to_observation(zone) for zone in irrigation_zones)
            for payload in observation_payloads:
                payload["sensor_values"] = {"telemetry_quality": telemetry_summary.get("status"), "telemetry_gap_count": telemetry_summary.get("gap_count", 0)}
            stand_summary = summarize_stands([row for row in detections if str(row.label).lower() in {"plant", "crop", "stand", "seedling"}], row_spacing_m=profile_snapshot.get("expected_row_spacing_m"), row_direction_deg=profile_snapshot.get("row_direction_deg"))
            run.counters = {**(run.counters or {}), "stand_summary": stand_summary, "rgb_product_status": {name: item["status"] for name, item in rgb_gates.items()}}
            current_features = {key: float(value) for key, value in (("canopy_pct", vision_summary.get("canopy_pct")), ("soil_pct", vision_summary.get("soil_pct")), ("visible_water_pct", vision_summary.get("visible_water_pct"))) if value is not None}
            profile_key = hashlib.sha256(json.dumps({key: profile_snapshot.get(key) for key in ("crop_type", "season", "growth_stage", "preset", "sensor_inventory")}, sort_keys=True).encode()).hexdigest()[:64]
            baseline = await db.scalar(select(AgricultureHealthBaseline).where(AgricultureHealthBaseline.field_id == flight.field_id, AgricultureHealthBaseline.profile_key == profile_key))
            anomaly = anomaly_signature(current=current_features, baseline=baseline.features if baseline and baseline.sample_count > 0 else None)
            if baseline is None:
                baseline = AgricultureHealthBaseline(field_id=flight.field_id, org_id=flight.org_id, profile_key=profile_key, features=current_features, sample_count=1, confidence=0.25, source_run_id=run.id)
                db.add(baseline); await db.flush()
            elif current_features and anomaly.get("status") != "candidate":
                baseline.features = {key: (float(baseline.features.get(key, value)) * baseline.sample_count + value) / (baseline.sample_count + 1) for key, value in current_features.items()}
                baseline.sample_count += 1; baseline.confidence = min(0.95, 0.25 + baseline.sample_count * 0.05); baseline.source_run_id = run.id
            run.quality_gate = {**(run.quality_gate or {}), "health_baseline": {"id": baseline.id, "profile_key": profile_key, "sample_count": baseline.sample_count}, "anomaly_signature": anomaly}
            if anomaly.get("status") == "candidate":
                observation_payloads.append({"observation_type": "abnormal_crop_health_signature", "geometry_geojson": {}, "georef_status": "unresolved", "area_m2": None, "severity": float(anomaly.get("confidence", 0.0)), "confidence": float(anomaly.get("confidence", 0.0)), "uncertainty": {"baseline_id": baseline.id, "deltas": anomaly.get("deltas", {})}, "first_detected": None, "last_detected": None, "trend": "current", "evidence_ids": [], "sensor_values": current_features, "model_version": "rgb_heuristic_fallback"})
            await db.execute(delete(AgricultureObservation).where(AgricultureObservation.run_id == run.id))
            await db.execute(delete(AgricultureAnalysisLayer).where(AgricultureAnalysisLayer.run_id == run.id))
            observations: list[AgricultureObservation] = []
            detections_by_id = {str(row.id): row for row in detections}
            for index, payload in enumerate(observation_payloads):
                legacy_zone_id = payload.pop("legacy_anomaly_zone_id", None)
                evidence_key = ",".join(sorted(str(item) for item in payload.get("evidence_ids", [])))
                record_id = stable_record_id(run.id, payload["observation_type"], evidence_key, index)
                evidence_detections = [
                    detections_by_id[evidence_id]
                    for evidence_id in (
                        str(item) for item in payload.get("evidence_ids", [])
                    )
                    if evidence_id in detections_by_id
                ]
                finding_job_ids = sorted(
                    {row.job_id for row in evidence_detections}
                )
                inference_provenance = []
                for finding_job_id in finding_job_ids:
                    link = inference_by_job.get(finding_job_id)
                    if link is None:
                        continue
                    snapshot = dict(link.inference_snapshot or {})
                    inference_provenance.append(
                        {
                            "inference_job_id": finding_job_id,
                            "capability_id": link.capability_id,
                            "capability_release_id": link.capability_release_id,
                            "source_video_id": link.video_id,
                            "source_checksum": snapshot.get("source_checksum"),
                            "vision_model_version_id": snapshot.get(
                                "vision_model_version_id"
                            ),
                            "model_hash": snapshot.get("model_checksum"),
                            "resolved_model_version": snapshot.get(
                                "resolved_model_version"
                            ),
                            "inference_profile": snapshot.get(
                                "inference_profile", {}
                            ),
                            "telemetry_match_version": snapshot.get(
                                "telemetry_match_version"
                            ),
                            "capability_contract_version": snapshot.get(
                                "capability_contract_version"
                            ),
                        }
                    )
                payload["provenance"] = {
                    "aggregation_version": "agriculture-aggregation.v1",
                    "analysis_run_id": run.id,
                    "inference_jobs": inference_provenance,
                }
                observations.append(AgricultureObservation(
                    id=record_id,
                    run_id=run.id,
                    flight_id=flight.id,
                    field_id=flight.field_id,
                    geometry=geometry_4326(payload.get("geometry_geojson", {})),
                    **payload,
                ))
                if legacy_zone_id is not None:
                    legacy_zone = next((zone for zone in irrigation_zones if zone.id == legacy_zone_id), None)
                    if legacy_zone is not None:
                        legacy_zone.canonical_observation_id = record_id
                for evidence_id in payload.get("evidence_ids", []):
                    detection = detections_by_id.get(str(evidence_id))
                    if detection is not None:
                        lineage = lineage_by_frame.get(detection.frame_index)
                        evidence_media_id = lineage.media_id if lineage else None
                        db.add(AgricultureObservationEvidence(id=stable_record_id("observation-evidence", record_id, detection.id), observation_id=record_id, detection_id=detection.id, frame_lineage_id=lineage.id if lineage else None, media_id=evidence_media_id, source_video_id=detection.video_id, evidence_path=None, frame_index=detection.frame_index, timestamp_seconds=detection.timestamp_seconds))
            db.add_all(observations)
            await db.flush()
            # EPSG:6933 is an equal-area projected CRS. GeoJSON remains WGS84/4326,
            # while hectares and square metres are never derived from degree units.
            for observation in observations:
                if observation.geometry is not None:
                    observation.area_m2 = float(await db.scalar(
                        select(func.ST_Area(func.ST_Transform(AgricultureObservation.geometry, 6933)))
                        .where(AgricultureObservation.id == observation.id)
                    ) or 0.0)
            by_type: dict[str, list[AgricultureObservation]] = defaultdict(list)
            for observation in observations: by_type[observation.observation_type].append(observation)
            output_size_bytes = 0
            for layer_name, layer_rows in by_type.items():
                features = [{"type": "Feature", "id": row.id, "geometry": row.geometry_geojson or None, "properties": {"observation_id": row.id, "severity": row.severity, "confidence": row.confidence, "area_m2": row.area_m2, "georef_status": row.georef_status, "review_state": row.review_state}} for row in layer_rows]
                geojson = {"type": "FeatureCollection", "features": features}
                output_size_bytes += len(json.dumps(geojson, sort_keys=True, separators=(",", ":")))
                checksum = hashlib.sha256(json.dumps(geojson, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                db.add(AgricultureAnalysisLayer(run_id=run.id, layer_name=layer_name, geojson=geojson, summary={"count": len(features), "area_m2": sum(row.area_m2 or 0 for row in layer_rows)}, checksum=checksum))
            if quality_features:
                quality_geojson = {"type": "FeatureCollection", "features": quality_features}
                quality_checksum = hashlib.sha256(json.dumps(quality_geojson, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                db.add(AgricultureAnalysisLayer(run_id=run.id, layer_name="quality", geojson=quality_geojson, summary={"count": len(quality_features), "reflight_count": sum(feature["properties"]["state"] == "blocked" for feature in quality_features)}, checksum=quality_checksum))
            fallback_layers = {"canopy_cover": "canopy_pct", "soil": "soil_pct", "standing_water": "visible_water_pct", "row_detection": "row_direction_confidence"}
            for layer_name, metric_name in fallback_layers.items():
                metric_value = vision_summary.get(metric_name)
                if metric_value is None:
                    continue
                features = [{"type": feature["type"], "id": feature["id"], "geometry": feature["geometry"], "properties": {**feature["properties"], metric_name: metric_value, "source": "rgb_heuristic_fallback"}} for feature in quality_features]
                geojson = {"type": "FeatureCollection", "features": features}
                output_size_bytes += len(json.dumps(geojson, sort_keys=True, separators=(",", ":")))
                checksum = hashlib.sha256(json.dumps(geojson, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                db.add(AgricultureAnalysisLayer(run_id=run.id, layer_name=layer_name, geojson=geojson, summary={metric_name: metric_value, "source": "rgb_heuristic_fallback", "count": len(features)}, checksum=checksum))
            inference_latency = perf_counter() - inference_started
            inference_stage.metrics = {"detection_count": len(detections), "observation_count": len(observations), "unresolved_count": sum(row.georef_status == "unresolved" for row in observations), "latency_seconds": inference_latency}
            inference_stage.status = "completed"; inference_stage.progress = 100.0; inference_stage.finished_at = datetime.now(UTC)
            georef_total = len(observations)
            georef_resolved = sum(row.georef_status == "resolved" for row in observations)
            run.counters = {**(run.counters or {}), "frames_received": len(lineage_rows), "frames_processed": len(quality_rows), "frames_dropped": sum(row.state == "blocked" for row in quality_rows), "frames_failed": sum(row.state == "failed" for row in quality_rows), "quality_rejection_count": sum(row.state == "blocked" for row in quality_rows), "inference_latency_seconds": inference_latency, "detection_count": len(detections), "observation_count": georef_total, "observation_area_m2": sum(row.area_m2 or 0.0 for row in observations), "output_size_bytes": output_size_bytes, "unresolved_observation_count": georef_total - georef_resolved, "georeference_success_count": georef_resolved, "georeference_success_rate": georef_resolved / georef_total if georef_total else 0.0, "dedup_ratio": max(0.0, 1.0 - (georef_total / len(detections))) if detections else 0.0}
            from backend.observability import prometheus_metrics
            prometheus_metrics.agriculture_georeference_rate.labels(stage="observation_aggregation").set(run.counters["georeference_success_rate"])
            prometheus_metrics.agriculture_observations_total.labels(stage="observation_aggregation").set(georef_total)
            prometheus_metrics.agriculture_inference_latency_seconds.labels(stage="observation_aggregation").observe(inference_latency)
            for outcome, count in (("received", len(lineage_rows)), ("processed", len(quality_rows)), ("dropped", run.counters["frames_dropped"]), ("failed", run.counters["frames_failed"])):
                prometheus_metrics.agriculture_frames_total.labels(stage="analysis", outcome=outcome).inc(count)
            prometheus_metrics.agriculture_quality_rejections_total.labels(reason="quality_gate").inc(run.counters["quality_rejection_count"])
            prometheus_metrics.agriculture_observation_area_m2.labels(stage="observation_aggregation").set(run.counters["observation_area_m2"])
            prometheus_metrics.agriculture_dedup_ratio.labels(stage="observation_aggregation").set(run.counters["dedup_ratio"])
            prometheus_metrics.agriculture_output_size_bytes.labels(stage="observation_aggregation").observe(output_size_bytes)
            run.progress = 100.0; run.status = "review" if observations else "completed"; run.error = None
            review_stage = await db.scalar(
                select(AgricultureAnalysisStage).where(
                    AgricultureAnalysisStage.run_id == run.id,
                    AgricultureAnalysisStage.stage_name == "review_ready",
                )
            )
            if review_stage is None:
                review_stage = AgricultureAnalysisStage(
                    run_id=run.id, stage_name="review_ready"
                )
                db.add(review_stage)
            review_stage.status = "completed"
            review_stage.progress = 100.0
            review_stage.started_at = review_stage.started_at or datetime.now(UTC)
            review_stage.finished_at = datetime.now(UTC)
            review_stage.metrics = {
                "observation_count": len(observations),
                "requires_review": bool(observations),
            }
            flight.quality_summary = quality_summary
            flight.coverage_summary = {**(flight.coverage_summary or {}), "observation_count": len(observations), "resolved_observation_count": sum(row.georef_status == "resolved" for row in observations)}
            if flight.status == "processing":
                await self.transition_flight(db, flight=flight, target="review")
            await db.commit()
            return run
        except Exception as exc:
            stage.status = "failed"; stage.error = str(exc)[:4000]; stage.finished_at = datetime.now(UTC)
            run.status = "failed"; run.error = str(exc)[:4000]; run.retry_count += 1
            run.audit_json = {**(run.audit_json or {}), "last_failure_at": datetime.now(UTC).isoformat(), "last_error": str(exc)[:1000]}
            from backend.observability import prometheus_metrics
            prometheus_metrics.agriculture_stage_failures_total.labels(stage=stage.stage_name, error_type=type(exc).__name__).inc()
            prometheus_metrics.agriculture_repeated_failures.labels(run_id=run.id).set(run.retry_count)
            if flight.status == "processing":
                await self.transition_flight(db, flight=flight, target="failed")
            await db.commit()
            raise

    @staticmethod
    def _read_evidence_file(path: str, maximum_bytes: int) -> bytes | None:
        source = Path(path).resolve()
        evidence_root = Path("backend/storage/video_analysis").resolve()
        if (
            not source.is_file()
            or evidence_root not in source.parents
            or source.stat().st_size > maximum_bytes
        ):
            return None
        return source.read_bytes()

    @staticmethod
    def _write_evidence_file(
        key: str,
        data: bytes,
        checksum: str,
        org_id: int | None,
        flight_id: str,
    ) -> None:
        agriculture_storage.validate_tenant_key(
            key, org_id=org_id, resource=f"flights/{flight_id}"
        )
        agriculture_storage.write_object(key, data, expected_checksum=checksum)
        agriculture_storage.validate_file_content(
            key, declared_content_type="image/jpeg"
        )

    @staticmethod
    def _sample_video_quality(videos: list[VideoSourceRef], run_id: str, flight_id: str) -> tuple[list[AgricultureFrameQuality], dict[str, Any], dict[str, Any]]:
        import cv2
        results: list[AgricultureFrameQuality] = []
        quality_results = []
        canopy_values: list[float] = []; soil_values: list[float] = []; water_values: list[float] = []; row_confidences: list[float] = []
        for video_number, video in enumerate(videos):
            capture = cv2.VideoCapture(video.storage_path)
            previous = None; frame_index = 0; sampled = 0
            while sampled < 120:
                ok, frame = capture.read()
                if not ok: break
                if frame_index % 5:
                    frame_index += 1; continue
                result = compute_frame_quality(frame, previous_bgr=previous)
                segmentation = segment_rgb_crop_soil_water(frame)
                if segmentation.get("status") == "pass":
                    canopy_values.append(float(segmentation["canopy_pct"])); soil_values.append(float(segmentation["soil_pct"])); water_values.append(float(segmentation["visible_water_pct"]))
                    row_confidences.append(float(infer_row_structure(segmentation["masks"]["crop"]).get("confidence", 0.0)))
                created_at = video.created_at if video.created_at.tzinfo is not None else video.created_at.replace(tzinfo=UTC)
                timestamp = created_at.astimezone(UTC) + timedelta(seconds=(frame_index / max(float(video.fps or 30), 1.0)))
                persisted_frame_index = video_number * 1_000_000 + frame_index
                results.append(AgricultureFrameQuality(id=stable_record_id(run_id, persisted_frame_index), run_id=run_id, flight_id=flight_id, frame_index=persisted_frame_index, timestamp_utc=timestamp, blur_score=result.metrics.get("blur_score"), motion_score=result.metrics.get("motion_score"), clipped_ratio=result.metrics.get("clipped_ratio"), black_ratio=result.metrics.get("black_ratio"), glare_ratio=result.metrics.get("glare_ratio"), contrast_score=result.metrics.get("contrast_score"), noise_score=result.metrics.get("noise_score"), duplicate_score=result.metrics.get("duplicate_score"), score=result.score, state=result.state, metrics={**result.metrics, "source_video_id": video.id, "source_frame_index": frame_index, "reasons": list(result.reasons)}))
                quality_results.append(result); previous = frame; sampled += 1; frame_index += 1
            capture.release()
        vision_summary = {"mode": "rgb_heuristic_fallback", "canopy_pct": sum(canopy_values) / len(canopy_values) if canopy_values else None, "soil_pct": sum(soil_values) / len(soil_values) if soil_values else None, "visible_water_pct": sum(water_values) / len(water_values) if water_values else None, "row_direction_confidence": sum(row_confidences) / len(row_confidences) if row_confidences else None, "sample_count": len(canopy_values)}
        return results, aggregate_quality(quality_results), vision_summary


agriculture_service = AgricultureService()
