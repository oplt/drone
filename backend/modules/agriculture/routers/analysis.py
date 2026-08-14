from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.core.pagination import decode_offset_cursor, encode_offset_cursor
from backend.modules.agriculture.analysis_orchestration import (
    AgricultureAnalysisReadinessError,
    agriculture_analysis_orchestration,
)
from backend.modules.agriculture.crop_insight_service import agriculture_crop_insight_service
from backend.modules.agriculture.events import emit_agriculture_event
from backend.modules.agriculture.finding_ops import (
    merge_observations,
    record_field_outcome,
    split_observation,
)
from backend.modules.agriculture.finding_ranking import (
    DEFAULT_FINDING_LIMIT,
    RANKING_POLICY_VERSION,
    rank_findings,
)
from backend.modules.agriculture.fusion_service import agriculture_fusion_service
from backend.modules.agriculture.governance import agriculture_governance_service
from backend.modules.agriculture.governance_models import AgricultureAssistantRun
from backend.modules.agriculture.inference_reuse import serialize_analysis_run
from backend.modules.agriculture.lifecycle import append_analysis_status_event
from backend.modules.agriculture.models import (
    AgricultureAnalysisLayer,
    AgricultureAnalysisRun,
    AgricultureAnalysisStage,
    AgricultureAnalysisVideoJob,
    AgricultureFieldProfile,
    AgricultureFlight,
    AgricultureMediaManifest,
    AgricultureObservation,
    new_id,
)
from backend.modules.agriculture.p4_models import (
    AgricultureCropRisk,
    AgricultureGrowthMetric,
    AgricultureGrowthStageEstimate,
    AgricultureYieldForecast,
)
from backend.modules.agriculture.p5_models import (
    AgricultureAgronomyRule,
    AgricultureExportJob,
    AgricultureFieldOutcome,
    AgricultureInspectionAction,
    AgriculturePrescriptionDraft,
    AgricultureReportSnapshot,
)
from backend.modules.agriculture.p5_service import agriculture_safety_service
from backend.modules.agriculture.queue import (
    AgricultureAnalysisQueueError,
    agriculture_analysis_queue,
)
from backend.modules.agriculture.report_service import (
    DECISION_REPORT_TEMPLATE_VERSION,
    REPORT_TEMPLATE_VERSION,
    build_decision_report_snapshot,
    build_report_snapshot,
)
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.routers import common as _common
from backend.modules.agriculture.routers.common import (
    AGRICULTURE_SCHEMA_VERSION,
)
from backend.modules.agriculture.schemas import (
    AgricultureAnalysisReadinessOut,
    AgricultureAssistantIn,
    AgricultureAssistantOut,
    AgricultureFlightOut,
    AgricultureLayerOut,
    AgricultureObservationOut,
    AgricultureObservationPage,
    AgricultureQualityOut,
    AgronomyRuleIn,
    AgronomyRuleOut,
    AnalysisProcessIn,
    AnalysisRunIn,
    AnalysisRunOut,
    AnalysisStageOut,
    AnalysisStageRetryIn,
    AnnotationIn,
    AnnotationOut,
    ApprovalIn,
    CalibrationIn,
    ComparableFlightOut,
    CropRiskIn,
    CropRiskOut,
    DatasetExportIn,
    DatasetExportOut,
    DatasetImportIn,
    FeedbackDecisionIn,
    FieldComparisonIn,
    FieldOutcomeIn,
    FieldOutcomeOut,
    FindingMergeIn,
    FindingSplitIn,
    FrameManifestIn,
    FusionIn,
    FusionResultOut,
    GrowthMetricIn,
    GrowthMetricOut,
    GrowthStageCorrectionIn,
    GrowthStageIn,
    GrowthStageOut,
    InspectionActionAssignmentIn,
    InspectionActionOut,
    InspectionPlanIn,
    InspectionPlanOut,
    InspectionRouteUpdateIn,
    ModelQualityReportIn,
    ModelVersionIn,
    ObservationAlertIn,
    ObservationAssignmentIn,
    ObservationFeedbackIn,
    ObservationFeedbackOut,
    PrescriptionIn,
    PrescriptionOut,
    RankedFindingOut,
    RankedFindingPage,
    ReportSnapshotIn,
    ReportSnapshotOut,
    ReviewAuditOut,
    ReviewIn,
    SensorCalibrationIn,
    SensorReadingBatchIn,
    SpectralBandIn,
    TemporalCompareIn,
    YieldForecastIn,
    YieldForecastOut,
)
from backend.modules.agriculture.segmentation_experiment import evaluate_segmentation_experiment
from backend.modules.agriculture.segmentation_schemas import SegmentationExperimentIn
from backend.modules.agriculture.sensor_models import (
    AgricultureFusionResult,
    AgricultureSensorCalibration,
    AgricultureSensorReading,
    AgricultureSpectralBand,
)
from backend.modules.agriculture.service import agriculture_service, utc
from backend.modules.agriculture.spatial import aggregate_features, web_mercator_tile_bounds
from backend.modules.agriculture.stage_operations import stage_input_checksum
from backend.modules.agriculture.storage import agriculture_storage
from backend.modules.agriculture.temporal import agriculture_temporal_service, summarize_changes
from backend.modules.agriculture.temporal_models import (
    AgricultureDatasetExport,
    AgricultureDatasetItem,
    AgricultureFlightAlignment,
    AgricultureObservationAnnotation,
    AgricultureObservationFeedback,
    AgricultureReviewAudit,
)
from backend.modules.agriculture.temporal_schemas import (
    AgricultureChangeOut,
    AgricultureComparisonOut,
)
from backend.modules.alerts.models import OperationalAlert
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.video_analysis.contracts import video_analysis_port
from backend.observability.instruments import observed_span
from backend.shared.json_responses import orjson_response

router = APIRouter()


@router.post("/calibrations", response_model=dict[str, Any])
async def register_calibration(payload: CalibrationIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    calibration = await agriculture_service.register_calibration(db, user=org_user.user, payload=payload)
    _common.emit_audit_event(event_name="agriculture_calibration_registered", action="register", resource_type="agriculture_calibration", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=calibration.id, extra={"checksum": calibration.checksum})
    return {"id": calibration.id, "camera_serial": calibration.camera_serial, "calibration_type": calibration.calibration_type, "checksum": calibration.checksum}


@router.post("/sensor-calibrations", response_model=dict[str, Any])
async def register_sensor_calibration(payload: SensorCalibrationIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)):
    existing = await db.get(AgricultureSensorCalibration, payload.id)
    if existing is not None and existing.org_id != getattr(org_user.user, "org_id", None):
        raise HTTPException(status_code=409, detail="Sensor calibration id already exists")
    if existing is not None:
        raise HTTPException(status_code=409, detail="Sensor calibration version already registered")
    calibration = AgricultureSensorCalibration(**payload.model_dump(), org_id=getattr(org_user.user, "org_id", None))
    db.add(calibration)
    await db.commit()
    _common.emit_audit_event(event_name="agriculture_sensor_calibration_registered", action="register", resource_type="agriculture_sensor_calibration", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=calibration.id, extra={"version": calibration.version})
    return {"id": calibration.id, "sensor_serial": calibration.sensor_serial, "sensor_type": calibration.sensor_type, "version": calibration.version, "checksum": calibration.checksum}


@router.post("/flights/{flight_id}/spectral-bands", response_model=list[dict[str, Any]])
async def register_spectral_bands(flight_id: str, payload: list[SpectralBandIn], db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    if not payload:
        raise HTTPException(status_code=422, detail="At least one spectral band is required")
    output = []
    for item in payload:
        media = await db.scalar(select(AgricultureMediaManifest).where(AgricultureMediaManifest.id == item.media_id, AgricultureMediaManifest.flight_id == flight.id))
        if media is None:
            raise HTTPException(status_code=422, detail=f"Media manifest not found for band {item.band_name}")
        duplicate = await db.scalar(select(AgricultureSpectralBand).where(AgricultureSpectralBand.media_id == item.media_id, AgricultureSpectralBand.band_name == item.band_name))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail=f"Band already registered: {item.media_id}/{item.band_name}")
        if item.calibration_id is not None and await db.get(AgricultureSensorCalibration, item.calibration_id) is None:
            raise HTTPException(status_code=422, detail=f"Calibration not found: {item.calibration_id}")
        values = item.model_dump(mode="json")
        values["metadata_json"] = values.pop("metadata")
        band = AgricultureSpectralBand(flight_id=flight.id, **values)
        db.add(band)
        output.append(band)
    await db.commit()
    return [{"id": band.id, "flight_id": flight.id, "media_id": band.media_id, "band_name": band.band_name, "alignment_status": band.alignment_status, "quality_status": band.quality_status, "calibration_id": band.calibration_id} for band in output]


@router.post("/flights/{flight_id}/sensor-readings", response_model=dict[str, Any])
async def ingest_sensor_readings(flight_id: str, payload: SensorReadingBatchIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    rows = []
    for item in payload.readings:
        values = item.model_dump(mode="json")
        values["timestamp_utc"] = utc(item.timestamp_utc)
        rows.append(AgricultureSensorReading(flight_id=flight.id, **values))
    db.add_all(rows)
    await db.commit()
    return {"flight_id": flight.id, "inserted": len(rows), "normalized_to_utc": True}


@router.get("/flights/{flight_id}/sensor-readings", response_model=list[dict[str, Any]])
async def list_sensor_readings(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    rows = list((await db.scalars(select(AgricultureSensorReading).where(AgricultureSensorReading.flight_id == flight.id).order_by(AgricultureSensorReading.timestamp_utc.desc()).limit(5000))).all())
    return [{"id": row.id, "sensor_type": row.sensor_type, "source": row.source, "sensor_serial": row.sensor_serial, "timestamp_utc": row.timestamp_utc, "scope_geojson": row.scope_geojson, "values": row.values, "units": row.units, "quality": row.quality, "stale_after_seconds": row.stale_after_seconds} for row in rows]


@router.get("/flights/{flight_id}/sensor-status", response_model=dict[str, Any])
async def get_sensor_status(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    return await agriculture_fusion_service.sensor_status(db, flight=flight)


@router.post("/flights/{flight_id}/frame-manifest", response_model=dict[str, Any], status_code=202)
async def register_frame_manifest(flight_id: str, payload: FrameManifestIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    await _common.enforce_rate_limit(key=f"agriculture:frames:{org_user.user.id}:{flight_id}", limit=settings.agriculture_rate_media_per_window, window_seconds=settings.agriculture_rate_window_seconds)
    try:
        return await agriculture_service.create_frame_manifest(db, flight=flight, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/flights/{flight_id}/finalize", response_model=AgricultureFlightOut)
async def finalize_flight(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    if flight.status not in {"archived", "published", "captured"}:
        try:
            await agriculture_service.transition_flight(db, flight=flight, target="captured")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        flight.quality_summary = {**(flight.quality_summary or {}), "status": "pending"}
        await db.commit()
        await db.refresh(flight)
        emit_agriculture_event("recording_stopped", flight_id=flight.id, status=flight.status)
    return flight


@router.post("/flights/{flight_id}/publish", response_model=AgricultureFlightOut)
async def publish_flight(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    try:
        await agriculture_service.transition_flight(db, flight=flight, target="published")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(flight)
    return flight


@router.post("/flights/{flight_id}/archive", response_model=AgricultureFlightOut)
async def archive_flight(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    try:
        await agriculture_service.transition_flight(db, flight=flight, target="archived")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(flight)
    return flight


@router.post("/flights/{flight_id}/analysis-runs", response_model=AnalysisRunOut, status_code=202)
async def create_analysis_run(flight_id: str, payload: AnalysisRunIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    inventory = await _common._media_inventory(flight, db)
    if not inventory["ready_for_processing"]:
        raise HTTPException(status_code=409, detail={"code": "MEDIA_INVENTORY_NOT_READY", "message": "Resolve missing, active, quarantined or storage-missing media before starting analysis.", "inventory": inventory})
    existing_idempotent_run = await agriculture_repository.get_run_by_key(
        db, flight_id=flight.id, key=payload.idempotency_key
    )
    if existing_idempotent_run is None:
        active_stmt = select(func.count()).select_from(AgricultureAnalysisRun).join(AgricultureFlight, AgricultureFlight.id == AgricultureAnalysisRun.flight_id).where(AgricultureAnalysisRun.status.in_(["queued", "orchestrating", "waiting_inference", "running"]))
        active_stmt = active_stmt.where(AgricultureFlight.org_id == flight.org_id) if flight.org_id is not None else active_stmt.where(AgricultureFlight.org_id.is_(None))
        if int(await db.scalar(active_stmt) or 0) >= settings.agriculture_max_active_analysis_runs_per_org:
            raise HTTPException(status_code=429, detail={"code": "AGRICULTURE_ANALYSIS_QUOTA_EXCEEDED", "message": "Organization active analysis quota exceeded"})
    if flight.status not in {"captured", "processing", "review", "failed"}:
        raise HTTPException(status_code=409, detail=f"Flight must be captured before analysis (status={flight.status})")
    try:
        requested_capabilities, model_releases, readiness = (
            await agriculture_analysis_orchestration.resolve_request(
                db,
                flight=flight,
                user=org_user.user,
                requested=payload.requested_analyses,
            )
        )
    except AgricultureAnalysisReadinessError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "AGRICULTURE_ANALYSIS_NOT_READY",
                "message": str(exc),
                "unavailable_capabilities": exc.unavailable,
                "readiness": exc.readiness,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_ANALYSIS_CAPABILITY", "message": str(exc)},
        ) from exc
    if flight.status == "captured":
        await agriculture_service.transition_flight(db, flight=flight, target="processing")
        await db.commit()
    sensors = set((flight.profile_snapshot or {}).get("sensor_inventory") or ["rgb"])
    calibration_ids = set((flight.profile_snapshot or {}).get("calibration_ids") or [])
    if sensors - {"rgb"}:
        now = datetime.now(UTC)
        valid_calibrations = set((await db.scalars(select(AgricultureSensorCalibration.id).where(AgricultureSensorCalibration.id.in_(calibration_ids), AgricultureSensorCalibration.org_id == flight.org_id, (AgricultureSensorCalibration.valid_from.is_(None) | (AgricultureSensorCalibration.valid_from <= now)), (AgricultureSensorCalibration.valid_until.is_(None) | (AgricultureSensorCalibration.valid_until > now))))).all()) if calibration_ids else set()
        if valid_calibrations != calibration_ids or not calibration_ids:
            raise HTTPException(status_code=409, detail={"code": "AGRICULTURE_CALIBRATION_GATE_BLOCKED", "message": "Non-RGB analysis requires current tenant-owned sensor calibration artifacts.", "sensor_inventory": sorted(sensors), "valid_calibration_ids": sorted(valid_calibrations)})
    await _common.enforce_rate_limit(key=f"agriculture:analysis:{org_user.user.id}:{flight_id}", limit=settings.agriculture_rate_analysis_runs_per_window, window_seconds=settings.agriculture_rate_window_seconds)
    with observed_span("agriculture.analysis_create", flight_id=flight.id, field_id=flight.field_id, mission_id=flight.mission_id):
        run = await agriculture_service.create_analysis_run(
            db,
            flight=flight,
            values={
                **payload.model_dump(),
                "requested_analyses": requested_capabilities,
                "model_versions": model_releases,
                "requested_by_user_id": org_user.user.id,
            },
        )
    calibration_artifacts = list((await db.scalars(select(AgricultureSensorCalibration).where(AgricultureSensorCalibration.id.in_(calibration_ids), AgricultureSensorCalibration.org_id == flight.org_id))).all()) if calibration_ids else []
    run.audit_json = {**(run.audit_json or {}), "capability_releases": model_releases, "readiness": readiness, "calibration_artifacts": [{"id": row.id, "sensor_serial": row.sensor_serial, "sensor_type": row.sensor_type, "version": row.version, "checksum": row.checksum, "valid_from": row.valid_from, "valid_until": row.valid_until} for row in calibration_artifacts]}
    await append_analysis_status_event(db, run, flight, "run.queued", "queued")
    await db.commit(); await db.refresh(run)
    try:
        await agriculture_analysis_orchestration.ensure_video_jobs(
            db,
            run=run,
            flight=flight,
            user=org_user.user,
        )
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:4000]
        run.finished_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "VIDEO_INFERENCE_SUBMISSION_FAILED",
                "message": "Required video inference could not be submitted.",
            },
        ) from exc
    _common.emit_audit_event(event_name="agriculture_analysis_requested", action="enqueue", resource_type="agriculture_analysis_run", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=run.id, extra={"flight_id": flight.id, "input_checksum": run.input_checksum})
    return run


@router.get(
    "/flights/{flight_id}/analysis-readiness",
    response_model=AgricultureAnalysisReadinessOut,
)
async def get_analysis_readiness(
    flight_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    flight = await _common._owned_flight(flight_id, org_user, db)
    return await agriculture_analysis_orchestration.readiness(
        db, flight=flight, user=org_user.user
    )


@router.get("/flights/{flight_id}/analysis-runs", response_model=list[AnalysisRunOut])
async def list_analysis_runs(flight_id: str, limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    runs = await agriculture_repository.list_runs(db, flight_id=flight_id, user=org_user.user, limit=limit)
    return [await serialize_analysis_run(db, run) for run in runs]


@router.get("/analysis-runs/{run_id}", response_model=AnalysisRunOut)
async def get_analysis_run(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return await serialize_analysis_run(db, run)


@router.post("/analysis-runs/{run_id}/process", response_model=AnalysisRunOut, status_code=202)
async def process_analysis_run(run_id: str, payload: AnalysisProcessIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    if payload.force:
        run.status = "queued"
        run.progress = 0.0
        run.error = None
        run.retry_count += 1
        stages = list((await db.scalars(select(AgricultureAnalysisStage).where(AgricultureAnalysisStage.run_id == run.id).with_for_update())).all())
        for stage in stages:
            stage.status = "queued"
            stage.progress = 0.0
            stage.error = None
            stage.dead_letter = False
            stage.dead_letter_at = None
            stage.retryable = True
        await db.commit()
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    try:
        await agriculture_analysis_orchestration.ensure_video_jobs(
            db,
            run=run,
            flight=flight,
            user=org_user.user,
            force=payload.force,
        )
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:4000]
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "VIDEO_INFERENCE_SUBMISSION_FAILED",
                "message": "Required video inference could not be submitted.",
            },
        ) from exc
    try:
        await append_analysis_status_event(db, run, flight, "run.queued", "process")
        await db.commit()
        agriculture_analysis_queue.enqueue(run_id=run.id, force=payload.force, cluster_radius_m=payload.cluster_radius_m)
    except AgricultureAnalysisQueueError as exc:
        run.status = "failed"
        run.error = str(exc)
        await db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return run


@router.post("/analysis-runs/{run_id}/cancel", response_model=AnalysisRunOut)
async def cancel_analysis_run(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    if run.status in {"completed", "review", "published", "failed", "cancelled"}:
        return run
    linked_job_ids = list(
        (
            await db.scalars(
                select(AgricultureAnalysisVideoJob.video_job_id).where(
                    AgricultureAnalysisVideoJob.run_id == run.id
                )
            )
        ).all()
    )
    await video_analysis_port.cancel_jobs(
        db, job_ids=linked_job_ids, user=org_user.user
    )
    run.status = "cancelled"
    run.error = "Cancelled by user"
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    await append_analysis_status_event(
        db, run, flight, "run.cancelled", "cancelled", {"reason": run.error}
    )
    await db.commit()
    _common.emit_audit_event(event_name="agriculture_analysis_cancelled", action="cancel", resource_type="agriculture_analysis_run", result="success", actor_type="user", actor_id=str(getattr(org_user.user, "id", "")), resource_id=run.id, extra={"flight_id": run.flight_id})
    return run


@router.post("/analysis-runs/{run_id}/replay", response_model=AnalysisRunOut, status_code=202)
async def replay_analysis_run(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    if run.status not in {"failed", "cancelled", "blocked_quality"}:
        raise HTTPException(status_code=409, detail="Only failed, cancelled, or quality-blocked runs can be replayed")
    run.status = "queued"
    run.progress = 0.0
    run.error = None
    run.retry_count += 1
    run.audit_json = {
        **(run.audit_json or {}),
        "replay": {"requested_at": datetime.now(UTC).isoformat(), "requested_by": org_user.user.id},
    }
    await db.commit()
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    try:
        await agriculture_analysis_orchestration.ensure_video_jobs(
            db,
            run=run,
            flight=flight,
            user=org_user.user,
            force=True,
        )
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:4000]
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "VIDEO_INFERENCE_SUBMISSION_FAILED",
                "message": "Required video inference could not be resubmitted.",
            },
        ) from exc
    try:
        agriculture_analysis_queue.replay(run_id=run.id)
    except AgricultureAnalysisQueueError as exc:
        run.status = "failed"
        run.error = str(exc)
        await db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _common.emit_audit_event(event_name="agriculture_analysis_replayed", action="replay", resource_type="agriculture_analysis_run", result="success", actor_type="user", actor_id=str(getattr(org_user.user, "id", "")), resource_id=run.id)
    return run


@router.post("/analysis-runs/{run_id}/fusion", response_model=list[FusionResultOut])
async def process_fusion(run_id: str, payload: FusionIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    return await agriculture_fusion_service.process(db, run=run, flight=flight, request=payload.model_dump())


@router.get("/analysis-runs/{run_id}/fusion-results", response_model=list[FusionResultOut])
async def list_fusion_results(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list((await db.scalars(select(AgricultureFusionResult).where(AgricultureFusionResult.run_id == run.id).order_by(AgricultureFusionResult.layer_name))).all())


@router.post("/analysis-runs/{run_id}/analytics/segmentation-experiment")
async def evaluate_crop_weed_segmentation(
    run_id: str,
    payload: SegmentationExperimentIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    result = evaluate_segmentation_experiment(payload.model_dump())
    geojson = {"type": "FeatureCollection", "features": []}
    checksum = hashlib.sha256(
        json.dumps({"geojson": geojson, "summary": result}, sort_keys=True).encode()
    ).hexdigest()
    layer = await db.scalar(
        select(AgricultureAnalysisLayer).where(
            AgricultureAnalysisLayer.run_id == run.id,
            AgricultureAnalysisLayer.layer_name == "crop_weed_segmentation_experiment",
        )
    )
    if layer is None:
        layer = AgricultureAnalysisLayer(
            run_id=run.id,
            layer_name="crop_weed_segmentation_experiment",
        )
        db.add(layer)
    layer.status = "research_only"
    layer.geojson = geojson
    layer.summary = result
    layer.checksum = checksum
    await db.commit()
    return result


@router.post("/analysis-runs/{run_id}/crop-risks", response_model=list[CropRiskOut])
async def process_crop_risks(run_id: str, payload: CropRiskIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    return await agriculture_crop_insight_service.process_crop_risk(db, run=run, flight=flight, request=payload.model_dump())


@router.get("/analysis-runs/{run_id}/crop-risks", response_model=list[CropRiskOut])
async def list_crop_risks(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list((await db.scalars(select(AgricultureCropRisk).where(AgricultureCropRisk.run_id == run.id).order_by(AgricultureCropRisk.created_at.desc()))).all())


@router.post("/crop-risks/{risk_id}/review", response_model=CropRiskOut)
async def review_crop_risk(risk_id: str, payload: ReviewIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    record = await db.get(AgricultureCropRisk, risk_id)
    if record is None: raise HTTPException(status_code=404, detail="Crop risk not found")
    run = await agriculture_repository.get_run(db, run_id=record.run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Crop risk not found")
    record.review_state = payload.status; record.review_note = payload.note; record.reviewed_by_user_id = getattr(org_user.user, "id", None); record.reviewed_at = datetime.now(UTC)
    await db.commit(); await db.refresh(record)
    return record


@router.post("/analysis-runs/{run_id}/growth-metrics", response_model=GrowthMetricOut)
async def process_growth_metric(run_id: str, payload: GrowthMetricIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    return await agriculture_crop_insight_service.process_growth_metric(db, run=run, flight=flight, request=payload.model_dump())


@router.get("/analysis-runs/{run_id}/growth-metrics", response_model=list[GrowthMetricOut])
async def list_growth_metrics(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list((await db.scalars(select(AgricultureGrowthMetric).where(AgricultureGrowthMetric.run_id == run.id).order_by(AgricultureGrowthMetric.metric_kind))).all())


@router.post("/analysis-runs/{run_id}/growth-stage", response_model=GrowthStageOut)
async def process_growth_stage(run_id: str, payload: GrowthStageIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    return await agriculture_crop_insight_service.process_growth_stage(db, run=run, flight=flight, request=payload.model_dump())


@router.get("/analysis-runs/{run_id}/growth-stage", response_model=GrowthStageOut)
async def get_growth_stage(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    record = await db.scalar(select(AgricultureGrowthStageEstimate).where(AgricultureGrowthStageEstimate.run_id == run.id))
    if record is None: raise HTTPException(status_code=404, detail="Growth-stage estimate not found")
    return record


@router.post("/growth-stage-estimates/{estimate_id}/correction", response_model=GrowthStageOut)
async def correct_growth_stage(estimate_id: str, payload: GrowthStageCorrectionIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    record = await db.get(AgricultureGrowthStageEstimate, estimate_id)
    if record is None: raise HTTPException(status_code=404, detail="Growth-stage estimate not found")
    run = await agriculture_repository.get_run(db, run_id=record.run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Growth-stage estimate not found")
    return await agriculture_crop_insight_service.correct_growth_stage(db, record=record, stage=payload.human_stage, note=payload.note, user_id=getattr(org_user.user, "id", None))


@router.post("/analysis-runs/{run_id}/yield-forecast", response_model=YieldForecastOut)
async def process_yield_forecast(run_id: str, payload: YieldForecastIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    return await agriculture_crop_insight_service.process_yield_forecast(db, run=run, flight=flight, request=payload.model_dump())


@router.get("/analysis-runs/{run_id}/yield-forecast", response_model=YieldForecastOut)
async def get_yield_forecast(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    record = await db.scalar(select(AgricultureYieldForecast).where(AgricultureYieldForecast.run_id == run.id))
    if record is None: raise HTTPException(status_code=404, detail="Yield forecast not found")
    return record


@router.post("/analysis-runs/{run_id}/inspection-actions", response_model=InspectionPlanOut)
async def create_inspection_plan(run_id: str, payload: InspectionPlanIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db); field = await _common._owned_field(flight.field_id, org_user, db)
    result = await agriculture_safety_service.inspection_plan(db, run=run, flight=flight, field=field, request=payload.model_dump())
    return result


@router.post("/analysis-runs/{run_id}/assistant", response_model=AgricultureAssistantOut, status_code=201)
async def run_agriculture_assistant(run_id: str, payload: AgricultureAssistantIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    result = await agriculture_governance_service.run(db, run=run, flight=flight, task=payload.task, question=payload.question, user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None))
    _common.emit_audit_event(event_name="agriculture_llm_output_created", action="create", resource_type="agriculture_assistant_run", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=result.id, extra={"run_id": run.id, "decision_status": result.decision_status, "context_checksum": result.context_checksum})
    return result


@router.get("/analysis-runs/{run_id}/assistant", response_model=list[AgricultureAssistantOut])
async def list_agriculture_assistant_runs(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list((await db.scalars(select(AgricultureAssistantRun).where(AgricultureAssistantRun.run_id == run.id).order_by(AgricultureAssistantRun.created_at.desc()))).all())


@router.get("/assistant-runs/{assistant_run_id}", response_model=AgricultureAssistantOut)
async def get_agriculture_assistant_run(assistant_run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    row = await db.get(AgricultureAssistantRun, assistant_run_id)
    if row is None or row.org_id != getattr(org_user.user, "org_id", None):
        raise HTTPException(status_code=404, detail="Agriculture assistant run not found")
    return row


@router.post("/assistant-runs/{assistant_run_id}/approval", response_model=AgricultureAssistantOut)
async def review_agriculture_assistant_run(assistant_run_id: str, payload: ApprovalIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    row = await db.get(AgricultureAssistantRun, assistant_run_id)
    if row is None or row.org_id != getattr(org_user.user, "org_id", None):
        raise HTTPException(status_code=404, detail="Agriculture assistant run not found")
    return await agriculture_governance_service.review(db, row=row, status=payload.status, note=payload.note, user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None))


@router.get("/analysis-runs/{run_id}/inspection-actions", response_model=list[InspectionActionOut])
async def list_inspection_actions(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list((await db.scalars(select(AgricultureInspectionAction).where(AgricultureInspectionAction.run_id == run.id).order_by(AgricultureInspectionAction.priority_rank))).all())


@router.put("/analysis-runs/{run_id}/inspection-actions/route", response_model=list[InspectionActionOut])
async def update_inspection_route(run_id: str, payload: InspectionRouteUpdateIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    try:
        return await agriculture_safety_service.update_inspection_route(
            db,
            run=run,
            ordered_action_ids=payload.ordered_action_ids,
            removed_action_ids=payload.removed_action_ids,
            reason=payload.reason,
            user_id=getattr(org_user.user, "id", None),
            org_id=getattr(org_user.user, "org_id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/analysis-runs/{run_id}/findings", response_model=RankedFindingPage)
async def list_ranked_findings(
    run_id: str,
    limit: int = Query(DEFAULT_FINDING_LIMIT, ge=1, le=100),
    include_withheld: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    observations = list(
        (
            await db.scalars(
                select(AgricultureObservation)
                .where(AgricultureObservation.run_id == run.id)
                .order_by(AgricultureObservation.id.asc())
            )
        ).all()
    )
    if not include_withheld:
        observations = [row for row in observations if not row.merged_into_id]
    changes = await agriculture_repository.list_changes(db, current_flight_id=flight.id, user=org_user.user)
    change_by_observation_id = {
        str(row.current_observation_id): row.state
        for row in changes
        if row.current_observation_id
    }
    profile = await db.scalar(select(AgricultureFieldProfile).where(AgricultureFieldProfile.field_id == flight.field_id))
    metadata = (profile.metadata_json if profile else None) or {}
    crop_context = {
        "crop_type": profile.crop_type if profile else None,
        "growth_stage": profile.growth_stage if profile else None,
        "priority_issue_types": metadata.get("priority_issue_types") or [],
    }
    ranked = rank_findings(
        observations,
        change_by_observation_id=change_by_observation_id,
        crop_context=crop_context,
        limit=limit,
        include_withheld=include_withheld,
    )
    hotspot_features = []
    for item in ranked:
        if item["display_status"] not in {"shown", "labeled_low_confidence"}:
            continue
        geometry = item.get("geometry_geojson") or {}
        if geometry.get("type") == "Feature":
            geometry = geometry.get("geometry") or {}
        hotspot_features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "finding_id": item["finding_id"],
                    "observation_id": item["observation_id"],
                    "rank": item["rank"],
                    "score": item["score"],
                    "display_status": item["display_status"],
                    "observation_type": item.get("observation_type"),
                    "severity": item.get("severity"),
                    "confidence": item.get("confidence"),
                },
            }
        )
    return RankedFindingPage(
        policy_version=RANKING_POLICY_VERSION,
        run_id=run.id,
        limit=limit,
        total_candidates=len(observations),
        items=[RankedFindingOut(**item) for item in ranked],
        hotspots={"type": "FeatureCollection", "features": hotspot_features},
    )


@router.post("/analysis-runs/{run_id}/findings/merge", response_model=AgricultureObservationOut)
async def merge_findings(run_id: str, payload: FindingMergeIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    primary = await agriculture_repository.get_observation(db, observation_id=payload.primary_observation_id, user=org_user.user)
    if primary is None or primary.run_id != run.id:
        raise HTTPException(status_code=404, detail="Primary observation not found")
    members = []
    for observation_id in payload.member_observation_ids:
        row = await agriculture_repository.get_observation(db, observation_id=observation_id, user=org_user.user)
        if row is None or row.run_id != run.id:
            raise HTTPException(status_code=404, detail=f"Member observation not found: {observation_id}")
        members.append(row)
    merge_observations(primary, members)
    db.add(
        AgricultureReviewAudit(
            observation_id=primary.id,
            actor_user_id=getattr(org_user.user, "id", None),
            org_id=getattr(org_user.user, "org_id", None),
            action="findings_merged",
            reason=payload.reason,
            payload={"member_observation_ids": [row.id for row in members]},
        )
    )
    await db.commit()
    await db.refresh(primary)
    return primary


@router.post("/observations/{observation_id}/split", response_model=list[AgricultureObservationOut])
async def split_finding(observation_id: str, payload: FindingSplitIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    source = await agriculture_repository.get_observation(db, observation_id=observation_id, user=org_user.user)
    if source is None:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    created = split_observation(source, [part.model_dump() for part in payload.parts], new_id_factory=new_id)
    for row in created:
        db.add(row)
    db.add(
        AgricultureReviewAudit(
            observation_id=source.id,
            actor_user_id=getattr(org_user.user, "id", None),
            org_id=getattr(org_user.user, "org_id", None),
            action="finding_split",
            reason=payload.reason,
            payload={"created_ids": [row.id for row in created]},
        )
    )
    await db.commit()
    for row in created:
        await db.refresh(row)
    return created


@router.post("/analysis-runs/{run_id}/field-outcomes", response_model=FieldOutcomeOut, status_code=201)
async def create_field_outcome(run_id: str, payload: FieldOutcomeIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    observation = await agriculture_repository.get_observation(db, observation_id=payload.observation_id, user=org_user.user)
    if observation is None or observation.run_id != run.id:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    model_version = payload.model_version or observation.model_version
    if not model_version and isinstance(run.model_versions, dict) and run.model_versions:
        model_version = next(iter(run.model_versions.values()), None)
        if isinstance(model_version, dict):
            model_version = str(model_version.get("version") or model_version.get("id") or "")
        else:
            model_version = str(model_version) if model_version is not None else None
    outcome = await record_field_outcome(
        db,
        org_id=getattr(org_user.user, "org_id", None),
        field_id=flight.field_id,
        flight_id=flight.id,
        run_id=run.id,
        observation_id=observation.id,
        outcome_status=payload.outcome_status,
        notes=payload.notes,
        model_version=model_version,
        capability_release_id=payload.capability_release_id,
        user_id=getattr(org_user.user, "id", None),
    )
    await db.commit()
    await db.refresh(outcome)
    return outcome


@router.get("/analysis-runs/{run_id}/field-outcomes", response_model=list[FieldOutcomeOut])
async def list_field_outcomes(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list(
        (
            await db.scalars(
                select(AgricultureFieldOutcome)
                .where(AgricultureFieldOutcome.run_id == run.id)
                .order_by(AgricultureFieldOutcome.created_at.desc())
            )
        ).all()
    )


@router.post("/inspection-actions/{action_id}/approval", response_model=InspectionActionOut)
async def approve_inspection_action(action_id: str, payload: ApprovalIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    action = await db.get(AgricultureInspectionAction, action_id)
    if action is None: raise HTTPException(status_code=404, detail="Inspection action not found")
    if await agriculture_repository.get_run(db, run_id=action.run_id, user=org_user.user) is None: raise HTTPException(status_code=404, detail="Inspection action not found")
    return await agriculture_safety_service.review_action(db, action=action, status=payload.status, note=payload.note, user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None))


@router.put("/inspection-actions/{action_id}/assignment", response_model=InspectionActionOut)
async def assign_inspection_action(action_id: str, payload: InspectionActionAssignmentIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    action = await db.get(AgricultureInspectionAction, action_id)
    if action is None or await agriculture_repository.get_run(db, run_id=action.run_id, user=org_user.user) is None:
        raise HTTPException(status_code=404, detail="Inspection action not found")
    action.assigned_to_user_id = payload.assigned_to_user_id
    action.due_at = payload.due_at
    await db.commit(); await db.refresh(action)
    return action


@router.post("/agronomy-rules", response_model=AgronomyRuleOut, status_code=201)
async def register_agronomy_rule(payload: AgronomyRuleIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    values = payload.model_dump(); status = values.pop("status")
    rule = await agriculture_safety_service.register_rule(db, payload={**values, "status": status}, org_id=getattr(org_user.user, "org_id", None), user_id=getattr(org_user.user, "id", None))
    if status == "approved": rule.approved_by_user_id = getattr(org_user.user, "id", None); rule.approved_at = datetime.now(UTC); await db.commit(); await db.refresh(rule)
    return rule


@router.get("/agronomy-rules", response_model=list[AgronomyRuleOut])
async def list_agronomy_rules(db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    stmt = select(AgricultureAgronomyRule).where(AgricultureAgronomyRule.org_id == getattr(org_user.user, "org_id", None)).order_by(AgricultureAgronomyRule.created_at.desc())
    return list((await db.scalars(stmt)).all())


@router.post("/agronomy-rules/{rule_id}/approval", response_model=AgronomyRuleOut)
async def approve_agronomy_rule(rule_id: str, payload: ApprovalIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    rule = await db.get(AgricultureAgronomyRule, rule_id)
    if rule is None or rule.org_id != getattr(org_user.user, "org_id", None): raise HTTPException(status_code=404, detail="Agronomy rule not found")
    rule.status = "approved" if payload.status == "approved" else "retired"; rule.approved_by_user_id = getattr(org_user.user, "id", None) if payload.status == "approved" else None; rule.approved_at = datetime.now(UTC) if payload.status == "approved" else None
    await db.commit(); await db.refresh(rule); return rule


@router.post("/analysis-runs/{run_id}/prescription-drafts", response_model=PrescriptionOut)
async def create_prescription_draft(run_id: str, payload: PrescriptionIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    return await agriculture_safety_service.prescription(db, run=run, flight=flight, request=payload.model_dump())


@router.get("/analysis-runs/{run_id}/prescription-drafts", response_model=list[PrescriptionOut])
async def list_prescription_drafts(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None: raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list((await db.scalars(select(AgriculturePrescriptionDraft).where(AgriculturePrescriptionDraft.run_id == run.id).order_by(AgriculturePrescriptionDraft.created_at.desc()))).all())


@router.post("/prescription-drafts/{draft_id}/approval", response_model=PrescriptionOut)
async def approve_prescription_draft(draft_id: str, payload: ApprovalIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    draft = await db.get(AgriculturePrescriptionDraft, draft_id)
    if draft is None or await agriculture_repository.get_run(db, run_id=draft.run_id, user=org_user.user) is None: raise HTTPException(status_code=404, detail="Prescription draft not found")
    if payload.status == "approved" and not draft.zones: raise HTTPException(status_code=422, detail="Cannot approve an empty or blocked prescription draft")
    return await agriculture_safety_service.review_prescription(db, draft=draft, status=payload.status, note=payload.note, user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None))


@router.get("/analysis-runs/{run_id}/quality", response_model=AgricultureQualityOut)
async def get_analysis_quality(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    stages = await agriculture_repository.list_stages(db, run_id=run_id)
    quality = run.quality_gate or {}
    return AgricultureQualityOut(run_id=run.id, status=str(quality.get("status", run.status)), score=float(quality.get("score", 0)), summary=quality, stages=stages)


@router.get("/analysis-runs/{run_id}/stages", response_model=list[AnalysisStageOut])
async def list_analysis_stages(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return await agriculture_repository.list_stages(db, run_id=run.id)


@router.post("/analysis-runs/{run_id}/stages/{stage_name}/retry", response_model=dict[str, Any], status_code=202)
@router.post("/analysis-runs/{run_id}/dead-letter/requeue", response_model=dict[str, Any], status_code=202)
async def retry_analysis_stage(run_id: str, payload: AnalysisStageRetryIn, stage_name: str = "", db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    # The dead-letter alias derives the failed stage from persisted audit metadata.
    if not stage_name:
        stage_name = str((run.audit_json or {}).get("dead_letter", {}).get("stage", ""))
    if stage_name not in agriculture_analysis_queue.STAGE_TASKS:
        raise HTTPException(status_code=422, detail="Unknown agriculture analysis stage")
    stage = await db.scalar(select(AgricultureAnalysisStage).where(AgricultureAnalysisStage.run_id == run.id, AgricultureAnalysisStage.stage_name == stage_name).with_for_update())
    if stage is None:
        stage = AgricultureAnalysisStage(run_id=run.id, stage_name=stage_name)
        db.add(stage)
        await db.flush()
    retry_keys = dict((run.counters or {}).get("stage_retry_keys", {}))
    existing = retry_keys.get(payload.idempotency_key)
    if existing:
        return {**existing, "idempotent_replay": True}
    if stage.status not in {"failed", "dead_letter", "queued", "running"} and run.status not in {"failed", "queued"}:
        raise HTTPException(status_code=409, detail=f"Stage '{stage_name}' is not recoverable from status '{stage.status}'")
    now = datetime.now(UTC).isoformat()
    stage.status = "queued"
    stage.progress = 0.0
    stage.error = None
    stage.retryable = True
    stage.dead_letter = False
    stage.dead_letter_at = None
    run.status = "queued"
    run.error = None
    run.retry_count += 1
    replay_checksum = stage_input_checksum(
        run,
        stage_name,
        upstream_checksum=stage.output_checksum,
        extra={"cluster_radius_m": float((run.counters or {}).get("cluster_radius_m", 8.0))},
    )
    stage.input_checksum = replay_checksum
    stage.execution_key = None
    await db.commit()
    try:
        task_id = agriculture_analysis_queue.enqueue_stage(
            stage=stage_name,
            run_id=run.id,
            input_checksum=replay_checksum,
            cluster_radius_m=float((run.counters or {}).get("cluster_radius_m", 8.0)),
            export_id=(
                str((stage.metrics or {}).get("export_id"))
                if (stage.metrics or {}).get("export_id")
                else None
            ),
        )
    except AgricultureAnalysisQueueError as exc:
        stage.status = "failed"
        stage.error = str(exc)
        await db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    stage.metrics = {**(stage.metrics or {}), "last_retry_reason": payload.reason, "last_retry_at": now, "recovery_task_id": task_id}
    response = {"run_id": run.id, "stage_name": stage_name, "status": "queued", "task_id": task_id, "reason": payload.reason}
    retry_keys[payload.idempotency_key] = response
    run.counters = {**(run.counters or {}), "stage_retry_keys": retry_keys, "last_recovery_at": now}
    run.audit_json = {**(run.audit_json or {}), "recovery": {"stage": stage_name, "task_id": task_id, "reason": payload.reason, "requested_at": now, "requested_by_user_id": org_user.user.id}}
    await db.commit()
    return response


@router.get("/analysis-runs/{run_id}/report")
async def get_analysis_report(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    observations = list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.run_id == run.id).order_by(AgricultureObservation.severity.desc()))).all())
    layers = list((await db.scalars(select(AgricultureAnalysisLayer).where(AgricultureAnalysisLayer.run_id == run.id).order_by(AgricultureAnalysisLayer.layer_name.asc()))).all())
    by_type: dict[str, int] = {}
    by_review: dict[str, int] = {}
    for row in observations:
        by_type[row.observation_type] = by_type.get(row.observation_type, 0) + 1
        by_review[row.review_state] = by_review.get(row.review_state, 0) + 1
    return {
        "schema_version": AGRICULTURE_SCHEMA_VERSION,
        "run_id": run.id,
        "flight_id": run.flight_id,
        "status": run.status,
        "progress": run.progress,
        "quality_gate": run.quality_gate or {},
        "counters": run.counters or {},
        "model_versions": run.model_versions or {},
        "calibration_versions": run.calibration_versions or {},
        "summary": {"observation_count": len(observations), "by_type": by_type, "by_review_state": by_review, "confirmed_count": by_review.get("confirmed", 0), "unreviewed_count": by_review.get("unreviewed", 0), "layer_names": [layer.layer_name for layer in layers]},
        "limitations": ["RGB candidate outputs require human review and validated model evidence.", "This report is not treatment advice or a substitute for agronomic inspection."],
    }


@router.post("/analysis-runs/{run_id}/report-snapshots", response_model=ReportSnapshotOut, status_code=201)
async def create_report_snapshot(run_id: str, payload: ReportSnapshotIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    if payload.template_key == "decision":
        if not payload.comparison_id:
            raise HTTPException(status_code=422, detail={"code": "COMPARISON_ID_REQUIRED", "message": "Decision reports require comparison_id"})
        alignment = await db.get(AgricultureFlightAlignment, payload.comparison_id)
        if alignment is None or alignment.current_flight_id != flight.id:
            raise HTTPException(status_code=404, detail="Agriculture comparison not found")
        await _common._owned_flight(alignment.current_flight_id, org_user, db)
        reference = await _common._owned_flight(alignment.reference_flight_id, org_user, db)
        reference_run = await db.scalar(
            select(AgricultureAnalysisRun)
            .where(AgricultureAnalysisRun.flight_id == reference.id)
            .order_by(AgricultureAnalysisRun.created_at.desc())
            .limit(1)
        )
        field = await _common._owned_field(flight.field_id, org_user, db)
        changes = await agriculture_repository.list_changes(db, current_flight_id=flight.id, user=org_user.user)
        pair_changes = [row for row in changes if row.reference_flight_id == alignment.reference_flight_id]
        observations = list(
            (
                await db.scalars(
                    select(AgricultureObservation)
                    .where(AgricultureObservation.run_id == run.id)
                    .order_by(AgricultureObservation.id.asc())
                )
            ).all()
        )
        reviewed = [row for row in observations if row.review_state in {"confirmed", "rejected", "relabelled"}]
        approved_actions = list(
            (
                await db.scalars(
                    select(AgricultureInspectionAction).where(
                        AgricultureInspectionAction.run_id == run.id,
                        AgricultureInspectionAction.status == "approved",
                    )
                )
            ).all()
        )
        change_by_observation_id = {
            str(row.current_observation_id): row.state
            for row in pair_changes
            if row.current_observation_id
        }
        profile = await db.scalar(select(AgricultureFieldProfile).where(AgricultureFieldProfile.field_id == flight.field_id))
        metadata = (profile.metadata_json if profile else None) or {}
        crop_context = {
            "crop_type": profile.crop_type if profile else None,
            "growth_stage": profile.growth_stage if profile else None,
            "priority_issue_types": metadata.get("priority_issue_types") or [],
        }
        findings = rank_findings(
            observations,
            change_by_observation_id=change_by_observation_id,
            crop_context=crop_context,
            limit=DEFAULT_FINDING_LIMIT,
        )
        snapshot_json, checksum = build_decision_report_snapshot(
            field=field,
            current_flight=flight,
            reference_flight=reference,
            current_run=run,
            reference_run=reference_run,
            comparability=alignment.comparability or {},
            changes=pair_changes,
            reviewed_observations=reviewed,
            approved_actions=approved_actions,
            findings=findings,
        )
        template_version = DECISION_REPORT_TEMPLATE_VERSION
    else:
        observations = list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.run_id == run.id).order_by(AgricultureObservation.id.asc()))).all())
        layers = list((await db.scalars(select(AgricultureAnalysisLayer).where(AgricultureAnalysisLayer.run_id == run.id).order_by(AgricultureAnalysisLayer.layer_name.asc()))).all())
        snapshot_json, checksum = build_report_snapshot(run=run, observations=observations, layers=layers, template_key=payload.template_key)
        template_version = REPORT_TEMPLATE_VERSION
    snapshot = AgricultureReportSnapshot(
        org_id=flight.org_id,
        field_id=flight.field_id,
        flight_id=flight.id,
        run_id=run.id,
        template_key=payload.template_key,
        template_version=template_version,
        snapshot_json=snapshot_json,
        checksum=checksum,
        created_by_user_id=org_user.user.id,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


@router.get("/analysis-runs/{run_id}/report-snapshots", response_model=list[ReportSnapshotOut])
async def list_report_snapshots(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list((await db.scalars(select(AgricultureReportSnapshot).where(AgricultureReportSnapshot.run_id == run.id).order_by(AgricultureReportSnapshot.created_at.desc()))).all())


@router.get("/report-snapshots/{snapshot_id}", response_model=ReportSnapshotOut)
async def get_report_snapshot(snapshot_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    snapshot = await db.get(AgricultureReportSnapshot, snapshot_id)
    if snapshot is None or snapshot.org_id != getattr(org_user.user, "org_id", None):
        raise HTTPException(status_code=404, detail="Agriculture report snapshot not found")
    return snapshot


@router.get("/analysis-runs/{run_id}/observations", response_model=AgricultureObservationPage)
async def list_analysis_observations(run_id: str, observation_type: str | None = None, min_severity: float | None = Query(default=None, ge=0, le=1), min_confidence: float | None = Query(default=None, ge=0, le=1), trend: str | None = Query(default=None, max_length=24), detected_from: datetime | None = None, detected_to: datetime | None = None, bbox: str | None = Query(default=None, description="min_lon,min_lat,max_lon,max_lat in EPSG:4326"), cursor: str | None = None, limit: int = Query(200, ge=1, le=500), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    try:
        offset = decode_offset_cursor(cursor)
        parsed_bbox = tuple(float(value) for value in bbox.split(",")) if bbox else None
        if parsed_bbox is not None and (len(parsed_bbox) != 4 or parsed_bbox[0] >= parsed_bbox[2] or parsed_bbox[1] >= parsed_bbox[3] or parsed_bbox[0] < -180 or parsed_bbox[2] > 180 or parsed_bbox[1] < -90 or parsed_bbox[3] > 90):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_OBSERVATION_CURSOR_OR_BBOX", "message": "Use a valid cursor and bbox=min_lon,min_lat,max_lon,max_lat"}) from exc
    rows, total = await agriculture_repository.list_observations(db, run_id=run_id, user=org_user.user, observation_type=observation_type, min_severity=min_severity, min_confidence=min_confidence, trend=trend, detected_from=detected_from, detected_to=detected_to, bbox=parsed_bbox, limit=limit, offset=offset)
    return AgricultureObservationPage(schema_version=AGRICULTURE_SCHEMA_VERSION, items=rows, total=total, next_cursor=encode_offset_cursor(offset + limit) if offset + len(rows) < total else None)


@router.get("/analysis-runs/{run_id}/layers/{layer}", response_model=AgricultureLayerOut)
async def get_analysis_layer(run_id: str, layer: str, response: Response, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    record = await agriculture_repository.get_layer(db, run_id=run_id, layer_name=layer, user=org_user.user)
    if record is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis layer not found")
    response.headers["ETag"] = f'"{record.checksum}"'
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return AgricultureLayerOut(run_id=record.run_id, layer=record.layer_name, status=record.status, geojson=record.geojson, summary=record.summary, checksum=record.checksum)


@router.get("/analysis-runs/{run_id}/spatial/layers")
async def list_spatial_layers(run_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    records = list((await db.scalars(select(AgricultureAnalysisLayer).where(AgricultureAnalysisLayer.run_id == run_id).order_by(AgricultureAnalysisLayer.layer_name.asc()))).all())
    return {"run_id": run_id, "layers": [{"layer": record.layer_name, "status": record.status, "summary": record.summary, "checksum": record.checksum, "generated_at": record.created_at} for record in records], "quality_gate": run.quality_gate or {}}


@router.get("/analysis-runs/{run_id}/spatial/viewport")
async def get_spatial_viewport(run_id: str, layer: str = "all", bbox: str | None = Query(default=None), zoom: int = Query(12, ge=0, le=24), min_severity: float = Query(0, ge=0, le=1), min_confidence: float = Query(0, ge=0, le=1), max_features: int = Query(2000, ge=50, le=5000), offset: int = Query(0, ge=0), page_size: int = Query(10000, ge=1, le=10000), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    parsed_bbox = _common._parse_spatial_bbox(bbox)
    observation_type = None if layer in {"all", "quality", "coverage", "health"} else layer
    rows, total = await agriculture_repository.list_spatial_observations(db, run_id=run_id, user=org_user.user, bbox=parsed_bbox, observation_type=observation_type, min_severity=min_severity, min_confidence=min_confidence, offset=offset, limit=page_size)
    geojson, unresolved = aggregate_features(rows, zoom=zoom, max_features=max_features)
    partial = total > len(rows) or unresolved
    payload = {"schema_version": AGRICULTURE_SCHEMA_VERSION, "run_id": run_id, "layer": layer, "zoom": zoom, "bbox": parsed_bbox, "total": total, "returned": len(rows), "offset": offset, "page_size": page_size, "next_offset": offset + len(rows) if offset + len(rows) < total else None, "total_kind": "exact", "partial": partial, "aggregation": "grid-cluster" if len(geojson.get("features", [])) < len(rows) else "raw", "geojson": geojson, "quality": {"status": "partial" if partial else "complete", "source": "canonical_observations"}}
    return orjson_response(payload)


@router.get("/analysis-runs/{run_id}/spatial/tiles/{z}/{x}/{y}")
async def get_spatial_tile(run_id: str, z: int, x: int, y: int, response: Response, layer: str = "all", min_severity: float = Query(0, ge=0, le=1), min_confidence: float = Query(0, ge=0, le=1), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    if z < 0 or x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        raise HTTPException(status_code=422, detail="Invalid XYZ tile coordinates")
    west, south, east, north = web_mercator_tile_bounds(z, x, y)
    observation_type = None if layer in {"all", "quality", "coverage", "health"} else layer
    rows, total = await agriculture_repository.list_spatial_observations(db, run_id=run_id, user=org_user.user, bbox=(west, south, east, north), observation_type=observation_type, min_severity=min_severity, min_confidence=min_confidence)
    geojson, unresolved = aggregate_features(rows, zoom=z, max_features=1000)
    checksum = hashlib.sha256(json.dumps(geojson, sort_keys=True, default=str).encode()).hexdigest()
    response.headers["ETag"] = f'"{checksum}"'
    response.headers["Cache-Control"] = "private, max-age=60, stale-while-revalidate=300"
    response.headers["Vary"] = "Authorization"
    payload = {"schema_version": AGRICULTURE_SCHEMA_VERSION, "run_id": run_id, "layer": layer, "tile": {"z": z, "x": x, "y": y}, "total": total, "partial": total > len(rows) or unresolved, "geojson": geojson, "checksum": checksum}
    return orjson_response(
        payload,
        headers={
            "etag": f'"{checksum}"',
            "cache-control": "private, max-age=60, stale-while-revalidate=300",
            "vary": "Authorization",
        },
    )


@router.get("/analysis-runs/{run_id}/layers/{layer}/download")
async def download_analysis_layer(run_id: str, layer: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    record = await agriculture_repository.get_layer(db, run_id=run_id, layer_name=layer, user=org_user.user)
    if record is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis layer not found")
    return orjson_response(
        record.geojson,
        headers={
            "content-disposition": f'attachment; filename="{layer}-{run_id}.geojson"',
            "etag": f'"{record.checksum}"',
            "cache-control": "private, max-age=31536000, immutable",
            "x-agriculture-schema-version": AGRICULTURE_SCHEMA_VERSION,
        },
    )


@router.get("/observations/{observation_id}", response_model=AgricultureObservationOut)
async def get_observation(observation_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    observation = await agriculture_repository.get_observation(db, observation_id=observation_id, user=org_user.user)
    if observation is None:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    return observation


@router.post("/observations/{observation_id}/review", response_model=AgricultureObservationOut)
async def review_observation(observation_id: str, payload: ReviewIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    observation = await agriculture_repository.get_observation(db, observation_id=observation_id, user=org_user.user)
    if observation is None:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    previous_state = observation.review_state
    observation.review_state = payload.status
    observation.review_label = payload.label
    observation.review_note = payload.note
    observation.reviewed_at = datetime.now(UTC)
    audit = AgricultureReviewAudit(observation_id=observation.id, actor_user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None), action="review", from_state=previous_state, to_state=payload.status, reason=payload.note, payload={"label": payload.label})
    db.add(audit)
    await db.commit(); await db.refresh(observation)
    emit_agriculture_event("observation_reviewed", flight_id=observation.flight_id, observation_id=observation.id, review_state=payload.status)
    _common.emit_audit_event(event_name="agriculture_observation_reviewed", action="review", resource_type="agriculture_observation", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=observation.id, extra={"from_state": previous_state, "to_state": payload.status})
    return observation


@router.put("/observations/{observation_id}/assignment", response_model=AgricultureObservationOut)
async def assign_observation(observation_id: str, payload: ObservationAssignmentIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    observation = await agriculture_repository.get_observation(db, observation_id=observation_id, user=org_user.user)
    if observation is None:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    previous = {"assigned_to_user_id": observation.assigned_to_user_id, "review_due_at": observation.review_due_at.isoformat() if observation.review_due_at else None}
    observation.assigned_to_user_id = payload.assigned_to_user_id
    observation.review_due_at = payload.review_due_at
    db.add(AgricultureReviewAudit(observation_id=observation.id, actor_user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None), action="assignment_changed", reason=payload.reason, payload={"from": previous, "to": {"assigned_to_user_id": payload.assigned_to_user_id, "review_due_at": payload.review_due_at.isoformat() if payload.review_due_at else None}}))
    await db.commit(); await db.refresh(observation)
    return observation


@router.get("/observations/{observation_id}/feedback", response_model=list[ObservationFeedbackOut])
async def list_observation_feedback(observation_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    return await agriculture_repository.list_feedback(db, observation_id=observation_id, user=org_user.user)


@router.post("/observations/{observation_id}/feedback", response_model=ObservationFeedbackOut, status_code=201)
async def submit_observation_feedback(observation_id: str, payload: ObservationFeedbackIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    observation = await agriculture_repository.get_observation(db, observation_id=observation_id, user=org_user.user)
    if observation is None:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    feedback = AgricultureObservationFeedback(observation_id=observation.id, actor_user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None), feedback_type=payload.feedback_type, proposed_label=payload.proposed_label, proposed_severity=payload.proposed_severity, proposed_zone_kind=payload.proposed_zone_kind, proposed_geometry_geojson=payload.proposed_geometry_geojson, comment=payload.comment, evidence_ids=payload.evidence_ids)
    db.add(feedback)
    db.add(AgricultureReviewAudit(observation_id=observation.id, actor_user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None), action="feedback_submitted", reason=payload.comment, payload={"feedback_type": payload.feedback_type, "feedback_id": feedback.id}))
    await db.commit(); await db.refresh(feedback)
    return feedback


@router.post("/feedback/{feedback_id}/decision", response_model=ObservationFeedbackOut)
async def decide_observation_feedback(feedback_id: str, payload: FeedbackDecisionIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    feedback = await db.get(AgricultureObservationFeedback, feedback_id)
    if feedback is None or feedback.org_id != getattr(org_user.user, "org_id", None):
        raise HTTPException(status_code=404, detail="Agriculture feedback not found")
    if feedback.status != "submitted":
        raise HTTPException(status_code=409, detail="Feedback has already been decided")
    observation = await agriculture_repository.get_observation(db, observation_id=feedback.observation_id, user=org_user.user)
    if observation is None:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    feedback.status = payload.status
    feedback.decision_note = payload.note
    feedback.decided_by_user_id = getattr(org_user.user, "id", None)
    feedback.decided_at = datetime.now(UTC)
    if payload.status == "accepted":
        latest = await db.scalar(select(AgricultureObservationAnnotation.version).where(AgricultureObservationAnnotation.observation_id == observation.id).order_by(AgricultureObservationAnnotation.version.desc()).limit(1))
        annotation = AgricultureObservationAnnotation(observation_id=observation.id, version=int(latest or 0) + 1, status="approved", label=feedback.proposed_label or observation.observation_type, severity=feedback.proposed_severity if feedback.proposed_severity is not None else observation.severity, geometry_geojson=feedback.proposed_geometry_geojson or observation.geometry_geojson, evidence_ids=feedback.evidence_ids or observation.evidence_ids, notes=feedback.comment, created_by_user_id=feedback.actor_user_id, approved_by_user_id=getattr(org_user.user, "id", None))
        db.add(annotation); await db.flush()
        feedback.annotation_id = annotation.id
        observation.review_state = "relabelled" if feedback.proposed_label else "confirmed"
        observation.review_label = feedback.proposed_label
        observation.review_note = feedback.comment
        if feedback.proposed_severity is not None: observation.severity = feedback.proposed_severity
        if feedback.proposed_zone_kind: observation.zone_kind = feedback.proposed_zone_kind
        if feedback.proposed_geometry_geojson: observation.geometry_geojson = feedback.proposed_geometry_geojson
        observation.reviewed_at = datetime.now(UTC)
    db.add(AgricultureReviewAudit(observation_id=observation.id, actor_user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None), action="feedback_decided", from_state="submitted", to_state=payload.status, reason=payload.note, payload={"feedback_id": feedback.id, "annotation_id": feedback.annotation_id}))
    await db.commit(); await db.refresh(feedback)
    return feedback


@router.post("/observations/{observation_id}/alert")
async def create_observation_alert(observation_id: str, payload: ObservationAlertIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    observation = await agriculture_repository.get_observation(db, observation_id=observation_id, user=org_user.user)
    if observation is None:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    dedupe_key = f"agriculture-observation:{observation.id}"
    alert = await db.scalar(select(OperationalAlert).where(OperationalAlert.org_id == getattr(org_user.user, "org_id", None), OperationalAlert.dedupe_key == dedupe_key, OperationalAlert.status != "resolved"))
    if alert is None:
        alert = OperationalAlert(org_id=getattr(org_user.user, "org_id", None), rule_type="agriculture_observation", dedupe_key=dedupe_key, source="agriculture", severity=payload.severity, status="open", title=payload.title, message=payload.message, due_at=payload.due_at, meta_data={"observation_id": observation.id, "run_id": observation.run_id, "flight_id": observation.flight_id, "field_id": observation.field_id, "review_state": observation.review_state})
        db.add(alert)
    else:
        alert.title = payload.title; alert.message = payload.message; alert.severity = payload.severity; alert.due_at = payload.due_at; alert.status = "open"; alert.resolved_at = None
    db.add(AgricultureReviewAudit(observation_id=observation.id, actor_user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None), action="alert_linked", reason=payload.message, payload={"dedupe_key": dedupe_key}))
    await db.commit(); await db.refresh(alert)
    return {"alert": alert, "observation_id": observation.id}


@router.get("/observations/{observation_id}/audit", response_model=list[ReviewAuditOut])
async def observation_audit(observation_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    return await agriculture_repository.list_audits(db, observation_id=observation_id, user=org_user.user)


@router.get("/observations/{observation_id}/annotations", response_model=list[AnnotationOut])
async def observation_annotations(observation_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    return await agriculture_repository.list_annotations(db, observation_id=observation_id, user=org_user.user)


@router.post("/observations/{observation_id}/annotations", response_model=AnnotationOut, status_code=201)
async def create_observation_annotation(observation_id: str, payload: AnnotationIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    observation = await agriculture_repository.get_observation(db, observation_id=observation_id, user=org_user.user)
    if observation is None: raise HTTPException(status_code=404, detail="Agriculture observation not found")
    latest = await db.scalar(select(AgricultureObservationAnnotation.version).where(AgricultureObservationAnnotation.observation_id == observation.id).order_by(AgricultureObservationAnnotation.version.desc()).limit(1))
    annotation = AgricultureObservationAnnotation(observation_id=observation.id, version=int(latest or 0) + 1, status=payload.status, label=payload.label, severity=payload.severity, geometry_geojson=payload.geometry_geojson, evidence_ids=payload.evidence_ids, notes=payload.notes, created_by_user_id=getattr(org_user.user, "id", None), approved_by_user_id=getattr(org_user.user, "id", None) if payload.status == "approved" else None)
    db.add(annotation)
    db.add(AgricultureReviewAudit(observation_id=observation.id, actor_user_id=getattr(org_user.user, "id", None), org_id=getattr(org_user.user, "org_id", None), action="annotation_created", from_state=None, to_state=payload.status, reason=payload.notes, annotation_version=annotation.version, payload={"label": payload.label}))
    await db.commit(); await db.refresh(annotation)
    return annotation


@router.post("/flights/{flight_id}/compare", response_model=AgricultureComparisonOut, status_code=202)
async def compare_flight(flight_id: str, payload: TemporalCompareIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    try:
        result = await agriculture_temporal_service.compare(db, current=flight, reference_flight_id=payload.reference_flight_id, min_quality_score=payload.min_quality_score)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    changes = await agriculture_repository.list_changes(db, current_flight_id=flight.id, user=org_user.user)
    alignment = await db.scalar(select(AgricultureFlightAlignment).where(AgricultureFlightAlignment.current_flight_id == flight.id, AgricultureFlightAlignment.reference_flight_id == result.get("reference_flight_id")))
    return AgricultureComparisonOut(id=alignment.id if alignment else None, status=result["status"], current_flight_id=flight.id, reference_flight_id=result.get("reference_flight_id"), alignment=result.get("alignment", {}), summary=result.get("summary", {}), changes=changes, comparability=result.get("comparability", {}), source_runs=result.get("source_runs", {}), methodology=result.get("methodology", {}))


@router.post("/fields/{field_id}/comparisons", response_model=AgricultureComparisonOut, status_code=202)
async def create_field_comparison(field_id: int, payload: FieldComparisonIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    current = await _common._owned_flight(payload.current_flight_id, org_user, db)
    if current.field_id != field_id:
        raise HTTPException(status_code=422, detail={"code": "COMPARISON_FIELD_MISMATCH", "message": "Current flight does not belong to this field"})
    if payload.reference_flight_id:
        reference = await _common._owned_flight(payload.reference_flight_id, org_user, db)
        if reference.field_id != field_id:
            raise HTTPException(status_code=422, detail={"code": "COMPARISON_FIELD_MISMATCH", "message": "Reference flight does not belong to this field"})
    try:
        result = await agriculture_temporal_service.compare(db, current=current, reference_flight_id=payload.reference_flight_id, min_quality_score=payload.min_quality_score)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "COMPARISON_NOT_POSSIBLE", "message": str(exc)}) from exc
    reference_id = result.get("reference_flight_id")
    alignment = await db.scalar(select(AgricultureFlightAlignment).where(AgricultureFlightAlignment.current_flight_id == current.id, AgricultureFlightAlignment.reference_flight_id == reference_id))
    changes = await agriculture_repository.list_changes(db, current_flight_id=current.id, user=org_user.user)
    return AgricultureComparisonOut(id=alignment.id if alignment else None, status=result["status"], current_flight_id=current.id, reference_flight_id=reference_id, alignment=result.get("alignment", {}), summary=result.get("summary", {}), changes=changes, comparability=result.get("comparability", {}), source_runs=result.get("source_runs", {}), methodology=result.get("methodology", {}))


@router.get("/comparisons/{comparison_id}", response_model=AgricultureComparisonOut)
async def get_comparison(comparison_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    alignment = await db.get(AgricultureFlightAlignment, comparison_id)
    if alignment is None:
        raise HTTPException(status_code=404, detail="Agriculture comparison not found")
    await _common._owned_flight(alignment.current_flight_id, org_user, db)
    changes = await agriculture_repository.list_changes(db, current_flight_id=alignment.current_flight_id, user=org_user.user)
    pair_changes = [row for row in changes if row.reference_flight_id == alignment.reference_flight_id]
    summary = summarize_changes(pair_changes)
    metrics = dict(alignment.metrics or {})
    source_runs = {
        key: str(value)
        for key, value in {
            "current": metrics.get("current_run_id"),
            "reference": metrics.get("reference_run_id"),
        }.items()
        if value
    }
    return AgricultureComparisonOut(id=alignment.id, status=metrics.get("comparison_status", alignment.status), current_flight_id=alignment.current_flight_id, reference_flight_id=alignment.reference_flight_id, alignment={"status": metrics.get("alignment_status", alignment.status), "method": alignment.method, "alignment_score": alignment.alignment_score, "overlap_pct": alignment.overlap_pct, "transform": alignment.transform, "failure_reasons": alignment.failure_reasons, "metrics": metrics}, summary=summary, changes=pair_changes, comparability=alignment.comparability or {}, source_runs=source_runs, methodology={"version": metrics.get("methodology_version", "observation_change.v1"), "alignment": alignment.method, "matching": metrics.get("matching_policy", "same_type_geometric_overlap")})


@router.get("/comparisons/{comparison_id}/layers/{layer}")
async def get_comparison_layers(comparison_id: str, layer: str, response: Response, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    alignment = await db.get(AgricultureFlightAlignment, comparison_id)
    if alignment is None:
        raise HTTPException(status_code=404, detail="Agriculture comparison not found")
    await _common._owned_flight(alignment.current_flight_id, org_user, db)
    metrics = dict(alignment.metrics or {})
    current_run = await db.get(AgricultureAnalysisRun, metrics.get("current_run_id")) if metrics.get("current_run_id") else await db.scalar(select(AgricultureAnalysisRun).where(AgricultureAnalysisRun.flight_id == alignment.current_flight_id).order_by(AgricultureAnalysisRun.created_at.desc()).limit(1))
    reference_run = await db.get(AgricultureAnalysisRun, metrics.get("reference_run_id")) if metrics.get("reference_run_id") else await db.scalar(select(AgricultureAnalysisRun).where(AgricultureAnalysisRun.flight_id == alignment.reference_flight_id).order_by(AgricultureAnalysisRun.created_at.desc()).limit(1))
    current_layer = await agriculture_repository.get_layer(db, run_id=current_run.id, layer_name=layer, user=org_user.user) if current_run else None
    reference_layer = await agriculture_repository.get_layer(db, run_id=reference_run.id, layer_name=layer, user=org_user.user) if reference_run else None
    if current_layer is None and reference_layer is None:
        raise HTTPException(status_code=404, detail="Comparison layer not found")
    checksum = hashlib.sha256(f"{current_layer.checksum if current_layer else ''}:{reference_layer.checksum if reference_layer else ''}:{alignment.id}".encode()).hexdigest()
    response.headers["ETag"] = f'"{checksum}"'
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return {"schema_version": AGRICULTURE_SCHEMA_VERSION, "comparison_id": alignment.id, "layer": layer, "alignment": alignment.transform, "current": current_layer.geojson if current_layer else None, "reference": reference_layer.geojson if reference_layer else None, "checksum": checksum}


@router.get("/comparisons/{comparison_id}/trends")
async def get_comparison_trends(comparison_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    comparison = await get_comparison(comparison_id, db, org_user)
    by_type: dict[str, dict[str, int]] = {}
    for change in comparison.changes:
        bucket = by_type.setdefault(change.observation_type, {})
        bucket[change.state] = bucket.get(change.state, 0) + 1
    return {"schema_version": AGRICULTURE_SCHEMA_VERSION, "comparison_id": comparison_id, "summary": comparison.summary, "by_type": by_type, "changes": comparison.changes}


@router.get("/flights/{flight_id}/comparisons", response_model=list[AgricultureChangeOut])
async def list_flight_comparisons(flight_id: str, limit: int = Query(2000, ge=1, le=5000), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_flight(flight_id, org_user, db)
    return await agriculture_repository.list_changes(db, current_flight_id=flight_id, user=org_user.user, limit=limit)


@router.get("/flights/{flight_id}/comparable-flights", response_model=list[ComparableFlightOut])
async def list_comparable_flights(
    flight_id: str,
    min_quality_score: float = Query(0.6, ge=0, le=1),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    flight = await _common._owned_flight(flight_id, org_user, db)
    rows = await agriculture_temporal_service.list_comparable_flights(
        db,
        current=flight,
        min_quality_score=min_quality_score,
        limit=limit,
    )
    return [ComparableFlightOut(**row) for row in rows]


@router.get("/fields/{field_id}/temporal-timeline", response_model=list[AgricultureFlightOut])
async def temporal_timeline(field_id: int, limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    await _common._owned_field(field_id, org_user, db)
    return await agriculture_repository.list_flights(db, field_id=field_id, user=org_user.user, limit=limit)


@router.post("/datasets/export", response_model=DatasetExportOut, status_code=201)
async def export_dataset(payload: DatasetExportIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    stmt = select(AgricultureObservationAnnotation).join(AgricultureObservation, AgricultureObservation.id == AgricultureObservationAnnotation.observation_id).join(AgricultureFlight, AgricultureFlight.id == AgricultureObservation.flight_id).where(AgricultureObservationAnnotation.status == "approved")
    if getattr(org_user.user, "org_id", None) is not None: stmt = stmt.where(AgricultureFlight.org_id == getattr(org_user.user, "org_id", None))
    else: stmt = stmt.where(AgricultureFlight.org_id.is_(None))
    if payload.annotation_ids: stmt = stmt.where(AgricultureObservationAnnotation.id.in_(payload.annotation_ids))
    annotations = list((await db.scalars(stmt.order_by(AgricultureObservationAnnotation.created_at.asc()))).all())
    if payload.annotation_ids and len(annotations) != len(set(payload.annotation_ids)): raise HTTPException(status_code=404, detail="One or more annotations not found or not approved")
    observation_ids = [row.observation_id for row in annotations]
    observation_rows = list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.id.in_(observation_ids)))).all()) if observation_ids else []
    flight_ids = {row.flight_id for row in observation_rows}
    flight_rows = list((await db.scalars(select(AgricultureFlight).where(AgricultureFlight.id.in_(flight_ids)))).all()) if flight_ids else []
    crops = sorted({str((row.profile_snapshot or {}).get("crop_type")) for row in flight_rows if (row.profile_snapshot or {}).get("crop_type")})
    stages = sorted({str((row.profile_snapshot or {}).get("growth_stage")) for row in flight_rows if (row.profile_snapshot or {}).get("growth_stage")})
    manifest = {"dataset_key": payload.dataset_key, "split": payload.split, "item_count": len(annotations), "holdout_field_count": len({row.field_id for row in observation_rows}), "holdout_flight_count": len(flight_ids), "crop_types": crops, "growth_stages": stages, "sensor_type": "rgb", "schema_version": "agriculture-annotation-v1", "source": "approved_annotations"}
    checksum = hashlib.sha256(json.dumps({"manifest": manifest, "ids": [row.id for row in annotations]}, sort_keys=True).encode()).hexdigest()
    export = AgricultureDatasetExport(org_id=getattr(org_user.user, "org_id", None), dataset_key=payload.dataset_key, direction="export", status="completed", manifest=manifest, checksum=checksum, created_by_user_id=getattr(org_user.user, "id", None))
    db.add(export); await db.flush()
    feedback_rows = list((await db.scalars(select(AgricultureObservationFeedback).where(AgricultureObservationFeedback.annotation_id.in_([row.id for row in annotations])))).all()) if annotations else []
    feedback_by_annotation = {row.annotation_id: row for row in feedback_rows if row.annotation_id}
    for annotation in annotations:
        feedback = feedback_by_annotation.get(annotation.id)
        db.add(AgricultureDatasetItem(export_id=export.id, annotation_id=annotation.id, feedback_id=feedback.id if feedback else None, split=payload.split, payload={"label": annotation.label, "severity": annotation.severity, "geometry_geojson": annotation.geometry_geojson, "evidence_ids": annotation.evidence_ids, "notes": annotation.notes, "annotation_version": annotation.version, "feedback_id": feedback.id if feedback else None}))
    await db.commit(); await db.refresh(export)
    return export


@router.get("/datasets/{export_id}/download")
async def download_dataset(export_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    export = await db.get(AgricultureDatasetExport, export_id)
    if export is None or (getattr(org_user.user, "org_id", None) is not None and export.org_id != getattr(org_user.user, "org_id", None)): raise HTTPException(status_code=404, detail="Dataset export not found")
    items = list((await db.scalars(select(AgricultureDatasetItem).where(AgricultureDatasetItem.export_id == export.id).order_by(AgricultureDatasetItem.id.asc()))).all())
    return orjson_response(
        {"dataset": export.manifest, "checksum": export.checksum, "items": [item.payload for item in items]},
        headers={
            "content-disposition": f'attachment; filename="{export.dataset_key}-{export.id}.json"',
            "etag": f'"{export.checksum}"',
            "cache-control": "private, max-age=31536000, immutable",
            "x-agriculture-schema-version": AGRICULTURE_SCHEMA_VERSION,
        },
    )


@router.post("/datasets/import", response_model=DatasetExportOut, status_code=201)
async def import_dataset(payload: DatasetImportIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    manifest = {"dataset_key": payload.dataset_key, "item_count": len(payload.items), "schema_version": "agriculture-annotation-v1", "source": "external_import", "split": payload.split, "crop_types": sorted(set(payload.crop_types)), "growth_stages": sorted(set(payload.growth_stages)), "sensor_type": payload.sensor_type, "holdout_field_count": payload.holdout_field_count, "holdout_flight_count": payload.holdout_flight_count, "source_checksum": payload.source_checksum}
    checksum = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    evidence_complete = payload.split in {"test", "shadow", "holdout"} and payload.holdout_field_count >= 3 and payload.holdout_flight_count >= 3 and bool(payload.crop_types) and bool(payload.growth_stages)
    record = AgricultureDatasetExport(org_id=getattr(org_user.user, "org_id", None), dataset_key=payload.dataset_key, direction="import", status="completed" if evidence_complete else "incomplete", manifest=manifest, checksum=checksum, created_by_user_id=getattr(org_user.user, "id", None))
    db.add(record); await db.commit(); await db.refresh(record)
    return record


@router.post("/models", response_model=dict[str, Any], status_code=201)
async def register_model(payload: ModelVersionIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)):
    raise HTTPException(
        status_code=410,
        detail={
            "code": "LEGACY_MODEL_REGISTRY_READ_ONLY",
            "message": "Create, train, evaluate, and deploy model artifacts through the Vision Models workspace.",
        },
    )


@router.post("/models/{model_version_id}/quality-reports", response_model=dict[str, Any], status_code=201)
async def create_model_quality_report(model_version_id: str, payload: ModelQualityReportIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)):
    raise HTTPException(
        status_code=410,
        detail={
            "code": "LEGACY_MODEL_REGISTRY_READ_ONLY",
            "message": "Evaluation provenance is owned by Vision model versions.",
        },
    )


@router.get("/assets")
async def get_asset(key: str, expires: int, signature: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    asset_stmt = select(AgricultureMediaManifest).join(AgricultureFlight, AgricultureFlight.id == AgricultureMediaManifest.flight_id).where(
        AgricultureMediaManifest.storage_key == key,
        AgricultureMediaManifest.retention_status == "active",
    )
    if getattr(org_user.user, "org_id", None) is None:
        asset_stmt = asset_stmt.where(AgricultureFlight.org_id.is_(None))
    else:
        asset_stmt = asset_stmt.where(AgricultureFlight.org_id == org_user.user.org_id)
    media = await db.scalar(asset_stmt)
    export = None
    if media is None:
        export_stmt = select(AgricultureExportJob).where(
            AgricultureExportJob.storage_key == key,
            AgricultureExportJob.status == "ready",
            (AgricultureExportJob.expires_at.is_(None) | (AgricultureExportJob.expires_at > datetime.now(UTC))),
        )
        if getattr(org_user.user, "org_id", None) is None:
            export_stmt = export_stmt.where(AgricultureExportJob.org_id.is_(None))
        else:
            export_stmt = export_stmt.where(AgricultureExportJob.org_id == org_user.user.org_id)
        export = await db.scalar(export_stmt)
    if media is None and export is None:
        raise HTTPException(status_code=404, detail="Agriculture asset unavailable")
    try:
        path = agriculture_storage.verify(key, expires, signature)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Agriculture asset unavailable") from exc
    checksum = media.checksum if media is not None else export.checksum
    if isinstance(path, str):
        return RedirectResponse(path, status_code=307, headers={"Cache-Control": "private, max-age=60", "X-Agriculture-Schema-Version": AGRICULTURE_SCHEMA_VERSION})
    return FileResponse(
        path,
        media_type=(media.content_type if media is not None else export.content_type),
        headers={
            "ETag": f'"{checksum}"',
            "Cache-Control": "private, max-age=900, immutable",
            "X-Agriculture-Schema-Version": AGRICULTURE_SCHEMA_VERSION,
        },
    )
