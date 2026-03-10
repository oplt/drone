from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import require_user
from backend.db.session import get_db
from backend.db.models import PatrolDetection, PatrolIncident

router = APIRouter(prefix="/api/patrol-debug", tags=["patrol-debug"])


class PatrolDetectionOut(BaseModel):
    id: int
    flight_id: int
    telemetry_id: Optional[int] = None
    created_at: Any
    frame_id: Optional[int] = None

    mission_task_type: str
    ai_task: str
    object_class: str
    anomaly_type: Optional[str] = None
    track_id: Optional[str] = None

    zone_name: Optional[str] = None
    checkpoint_index: Optional[int] = None
    confidence: float

    bbox_xyxy: dict[str, Any]
    centroid_xy: dict[str, Any]

    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: Optional[float] = None
    heading: Optional[float] = None
    groundspeed: Optional[float] = None

    source: str
    snapshot_path: Optional[str] = None
    clip_path: Optional[str] = None

    model_name: Optional[str] = None
    model_version: Optional[str] = None
    meta_data: dict[str, Any]

    class Config:
        from_attributes = True


class PatrolIncidentOut(BaseModel):
    id: int
    flight_id: int
    opened_at: Any
    updated_at: Any
    closed_at: Optional[Any] = None

    status: str
    mission_task_type: str
    incident_type: str
    primary_object_class: Optional[str] = None
    primary_track_id: Optional[str] = None
    ai_task: Optional[str] = None

    zone_name: Optional[str] = None
    checkpoint_index: Optional[int] = None

    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None

    peak_confidence: Optional[float] = None
    detection_count: int

    first_detection_id: Optional[int] = None
    last_detection_id: Optional[int] = None

    snapshot_path: Optional[str] = None
    clip_path: Optional[str] = None
    last_alert_id: Optional[int] = None
    summary: dict[str, Any]

    class Config:
        from_attributes = True


class DetectionListResponse(BaseModel):
    items: list[PatrolDetectionOut]
    total: int


class IncidentListResponse(BaseModel):
    items: list[PatrolIncidentOut]
    total: int


class IncidentEvidenceOut(BaseModel):
    incident_id: int
    flight_id: int
    incident_type: str
    status: str
    opened_at: Any
    snapshot_path: Optional[str] = None
    clip_path: Optional[str] = None
    zone_name: Optional[str] = None
    checkpoint_index: Optional[int] = None
    peak_confidence: Optional[float] = None


class IncidentEvidenceListResponse(BaseModel):
    items: list[IncidentEvidenceOut]
    total: int


@router.get("/detections/by-flight/{flight_id}", response_model=DetectionListResponse)
async def list_detections_by_flight(
    flight_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    anomaly_type: Optional[str] = Query(default=None),
    ai_task: Optional[str] = Query(default=None),
    object_class: Optional[str] = Query(default=None),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [PatrolDetection.flight_id == flight_id]

    if anomaly_type:
        filters.append(PatrolDetection.anomaly_type == anomaly_type)
    if ai_task:
        filters.append(PatrolDetection.ai_task == ai_task)
    if object_class:
        filters.append(PatrolDetection.object_class == object_class)

    count_stmt = select(func.count()).select_from(PatrolDetection).where(*filters)
    total = await db.scalar(count_stmt) or 0

    stmt = (
        select(PatrolDetection)
        .where(*filters)
        .order_by(desc(PatrolDetection.created_at), desc(PatrolDetection.id))
        .offset(offset)
        .limit(limit)
    )
    items = (await db.scalars(stmt)).all()

    return DetectionListResponse(
        items=[PatrolDetectionOut.model_validate(item) for item in items],
        total=int(total),
    )


@router.get("/incidents", response_model=IncidentListResponse)
async def list_incidents_by_status(
    status: str = Query(default="open"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    flight_id: Optional[int] = Query(default=None),
    incident_type: Optional[str] = Query(default=None),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []

    if status != "all":
        filters.append(PatrolIncident.status == status)
    if flight_id is not None:
        filters.append(PatrolIncident.flight_id == flight_id)
    if incident_type:
        filters.append(PatrolIncident.incident_type == incident_type)

    count_stmt = select(func.count()).select_from(PatrolIncident).where(*filters)
    total = await db.scalar(count_stmt) or 0

    stmt = (
        select(PatrolIncident)
        .where(*filters)
        .order_by(desc(PatrolIncident.updated_at), desc(PatrolIncident.id))
        .offset(offset)
        .limit(limit)
    )
    items = (await db.scalars(stmt)).all()

    return IncidentListResponse(
        items=[PatrolIncidentOut.model_validate(item) for item in items],
        total=int(total),
    )


@router.get("/incidents/latest-evidence", response_model=IncidentEvidenceListResponse)
async def latest_incident_evidence_paths(
    limit: int = Query(default=50, ge=1, le=200),
    flight_id: Optional[int] = Query(default=None),
    status: str = Query(default="all"),
    with_files_only: bool = Query(default=True),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []

    if flight_id is not None:
        filters.append(PatrolIncident.flight_id == flight_id)
    if status != "all":
        filters.append(PatrolIncident.status == status)
    if with_files_only:
        filters.append(
            (PatrolIncident.snapshot_path.is_not(None)) |
            (PatrolIncident.clip_path.is_not(None))
        )

    stmt = (
        select(PatrolIncident)
        .where(*filters)
        .order_by(desc(PatrolIncident.updated_at), desc(PatrolIncident.id))
        .limit(limit)
    )
    items = (await db.scalars(stmt)).all()

    return IncidentEvidenceListResponse(
        items=[
            IncidentEvidenceOut(
                incident_id=item.id,
                flight_id=item.flight_id,
                incident_type=item.incident_type,
                status=item.status,
                opened_at=item.opened_at,
                snapshot_path=item.snapshot_path,
                clip_path=item.clip_path,
                zone_name=item.zone_name,
                checkpoint_index=item.checkpoint_index,
                peak_confidence=item.peak_confidence,
            )
            for item in items
        ],
        total=len(items),
    )


@router.get("/incidents/{incident_id}", response_model=PatrolIncidentOut)
async def get_incident_detail(
    incident_id: int,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(PatrolIncident, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Patrol incident not found")
    return PatrolIncidentOut.model_validate(row)