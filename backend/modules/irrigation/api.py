from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.infrastructure.cache.locks import distributed_lock
from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.irrigation.job_repository import IrrigationJobRepository
from backend.modules.irrigation.models import IrrigationProcessingJob
from backend.modules.irrigation.queue import IrrigationQueueError, enqueue_irrigation_processing
from backend.modules.irrigation.repository import IrrigationRepository
from backend.modules.irrigation.service.processing import irrigation_service

logger = logging.getLogger(__name__)
irrigation_repository = IrrigationRepository()

router = APIRouter(prefix="/irrigation", tags=["irrigation"])


class CaptureRecordOut(BaseModel):
    id: int
    mission_id: str
    image_uri: str
    timestamp_utc: datetime
    lat: float
    lon: float
    alt_m: float | None = None
    yaw_deg: float | None = None
    pitch_deg: float | None = None
    roll_deg: float | None = None
    waypoint_seq: int | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    meta_data: dict[str, Any] = Field(default_factory=dict)


class AnomalyZoneOut(BaseModel):
    id: int
    type: str
    severity: float
    confidence: float
    area_m2: float | None = None
    centroid_lat: float
    centroid_lon: float
    polygon_geojson: dict[str, Any]
    evidence_image_ids: list[Any] = Field(default_factory=list)
    meta_data: dict[str, Any] = Field(default_factory=dict)


class InspectionPointOut(BaseModel):
    id: int
    zone_id: int | None = None
    lat: float
    lon: float
    label: str
    priority: float
    meta_data: dict[str, Any] = Field(default_factory=dict)


class ProcessedFieldLayerOut(BaseModel):
    id: int
    mission_id: str
    status: str
    capture_count: int
    stitched_image_uri: str | None = None
    footprints_geojson: dict[str, Any] = Field(default_factory=dict)
    tile_manifest: dict[str, Any] = Field(default_factory=dict)
    bounds_geojson: dict[str, Any] = Field(default_factory=dict)
    resolution_m_per_px: float | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    completed_at: datetime | None = None


class IrrigationMissionSummaryOut(BaseModel):
    mission_id: str
    status: str
    capture_count: int
    captures: list[CaptureRecordOut] = Field(default_factory=list)
    layer: ProcessedFieldLayerOut | None = None
    anomaly_zones: list[AnomalyZoneOut] = Field(default_factory=list)
    inspection_points: list[InspectionPointOut] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class IrrigationProcessingJobOut(BaseModel):
    id: str
    mission_id: str
    input_checksum: str
    force: bool
    status: str
    celery_task_id: str | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


def _parse_timestamp(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid timestamp_utc format") from exc


async def _owned_mission_or_404(
    db: AsyncSession,
    *,
    mission_id: str,
    org_user: OrgUser,
):
    mission = await irrigation_service.get_owned_mission(
        db,
        mission_id=mission_id,
        user=org_user.user,
    )
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.post("/captures", response_model=CaptureRecordOut)
async def create_capture_record(
    mission_id: str = Form(...),
    timestamp_utc: str | None = Form(default=None),
    lat: float = Form(...),
    lon: float = Form(...),
    alt_m: float | None = Form(default=None),
    yaw_deg: float | None = Form(default=None),
    pitch_deg: float | None = Form(default=None),
    roll_deg: float | None = Form(default=None),
    waypoint_seq: int | None = Form(default=None),
    meta_data: str | None = Form(default=None),
    image: UploadFile = File(...),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> CaptureRecordOut:
    mission = await _owned_mission_or_404(db, mission_id=mission_id, org_user=org_user)
    parsed_timestamp = _parse_timestamp(timestamp_utc)
    try:
        persisted = await irrigation_service.persist_upload(
            mission_id=mission_id,
            upload=image,
            timestamp_utc=parsed_timestamp,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        meta_payload = json.loads(meta_data) if meta_data else {}
    except json.JSONDecodeError as exc:
        await run_blocking(
            persisted.image_path.unlink,
            missing_ok=True,
            boundary="filesystem",
            operation="irrigation_upload_cleanup",
            timeout_s=30.0,
        )
        raise HTTPException(status_code=422, detail="meta_data must be valid JSON") from exc
    try:
        capture = await irrigation_service.register_capture(
            db,
            mission=mission,
            image_uri=persisted.public_uri,
            timestamp_utc=parsed_timestamp,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            yaw_deg=yaw_deg,
            pitch_deg=pitch_deg,
            roll_deg=roll_deg,
            waypoint_seq=waypoint_seq,
            frame_width=persisted.width,
            frame_height=persisted.height,
            meta_data=meta_payload,
        )
        capture = await irrigation_repository.save_capture(db, capture=capture)
    except Exception:
        await run_blocking(
            persisted.image_path.unlink,
            missing_ok=True,
            boundary="filesystem",
            operation="irrigation_capture_cleanup",
            timeout_s=30.0,
        )
        raise
    return CaptureRecordOut.model_validate(capture, from_attributes=True)


@router.get("/missions/{mission_id}/captures", response_model=Page[CaptureRecordOut])
async def list_mission_captures(
    mission_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> Page[CaptureRecordOut]:
    await _owned_mission_or_404(db, mission_id=mission_id, org_user=org_user)
    page_limit = clamp_page_limit(limit, maximum=200)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    captures = await irrigation_service.list_captures(
        db,
        mission_id=mission_id,
        limit=page_limit + 1,
        offset=page_offset,
    )
    return page_from_offset(
        [CaptureRecordOut.model_validate(item, from_attributes=True) for item in captures],
        limit=page_limit,
        offset=page_offset,
    )


async def _enqueue_processing_job(
    db: AsyncSession,
    *,
    mission_id: str,
    org_user: OrgUser,
    force: bool,
) -> IrrigationProcessingJob:
    mission = await _owned_mission_or_404(db, mission_id=mission_id, org_user=org_user)
    captures = await irrigation_service.list_captures(db, mission_id=mission_id)
    input_checksum = irrigation_service.capture_input_checksum(captures)
    repository = IrrigationJobRepository()

    async with distributed_lock(f"lock:irrigation:enqueue:{mission_id}:{input_checksum}"):
        existing = await repository.find_reusable(
            db,
            mission_id=mission_id,
            input_checksum=input_checksum,
            force=force,
        )
        if existing is not None:
            if not existing.celery_task_id:
                try:
                    existing.celery_task_id = enqueue_irrigation_processing(existing.id)
                    await db.commit()
                    await db.refresh(existing)
                except IrrigationQueueError as exc:
                    await repository.mark_finished(db, existing.id, status="failed", error=str(exc))
                    raise HTTPException(
                        status_code=503, detail="Irrigation worker unavailable"
                    ) from exc
            return existing

        layer = await irrigation_service.get_or_create_layer(db, mission=mission)
        layer.status = "queued"
        layer.error = None
        layer.capture_count = len(captures)
        job = await repository.create(
            db,
            job_id=uuid4().hex,
            mission_id=mission_id,
            org_id=mission.org_id,
            user_id=org_user.user.id,
            input_checksum=input_checksum,
            force=force,
        )
        await db.commit()
        try:
            job.celery_task_id = enqueue_irrigation_processing(job.id)
            await db.commit()
            await db.refresh(job)
        except IrrigationQueueError as exc:
            await repository.mark_finished(db, job.id, status="failed", error=str(exc))
            layer.status = "failed"
            layer.error = "Irrigation worker unavailable"
            await db.commit()
            raise HTTPException(status_code=503, detail="Irrigation worker unavailable") from exc
        return job


@router.post(
    "/missions/{mission_id}/process",
    response_model=IrrigationProcessingJobOut,
    status_code=202,
)
async def process_irrigation_mission(
    mission_id: str,
    force: bool = False,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> IrrigationProcessingJobOut:
    job = await _enqueue_processing_job(
        db,
        mission_id=mission_id,
        org_user=org_user,
        force=force,
    )
    return IrrigationProcessingJobOut.model_validate(job, from_attributes=True)


@router.post(
    "/missions/{mission_id}/process-job",
    response_model=IrrigationProcessingJobOut,
    status_code=202,
)
async def enqueue_irrigation_mission_processing(
    mission_id: str,
    force: bool = False,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> IrrigationProcessingJobOut:
    """Queue heavy processing; worker owns all image decoding and analytics."""
    job = await _enqueue_processing_job(
        db,
        mission_id=mission_id,
        org_user=org_user,
        force=force,
    )
    return IrrigationProcessingJobOut.model_validate(job, from_attributes=True)


@router.get("/processing-jobs/{job_id}", response_model=IrrigationProcessingJobOut)
async def get_irrigation_processing_job(
    job_id: str,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> IrrigationProcessingJobOut:
    job = await IrrigationJobRepository().get_owned(db, job_id=job_id, org_id=org_user.org_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Irrigation processing job not found")
    return IrrigationProcessingJobOut.model_validate(job, from_attributes=True)


@router.get("/missions/{mission_id}/summary", response_model=IrrigationMissionSummaryOut)
async def get_irrigation_mission_summary(
    mission_id: str,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> IrrigationMissionSummaryOut:
    await _owned_mission_or_404(db, mission_id=mission_id, org_user=org_user)
    captures, layer, zones, points = await irrigation_repository.summary_components(
        db, mission_id=mission_id
    )

    status = "pending"
    summary = {"status": "pending"}
    if layer is not None:
        status = layer.status
        summary = layer.summary or {"status": status}
    elif captures:
        status = "captured"
        summary = {"status": "captured", "capture_count": len(captures)}

    return IrrigationMissionSummaryOut(
        mission_id=mission_id,
        status=status,
        capture_count=len(captures),
        captures=[CaptureRecordOut.model_validate(item, from_attributes=True) for item in captures],
        layer=ProcessedFieldLayerOut.model_validate(layer, from_attributes=True) if layer else None,
        anomaly_zones=[AnomalyZoneOut.model_validate(item, from_attributes=True) for item in zones],
        inspection_points=[
            InspectionPointOut.model_validate(item, from_attributes=True) for item in points
        ],
        summary=summary,
    )
