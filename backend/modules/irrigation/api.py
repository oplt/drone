from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.irrigation.application import irrigation_application
from backend.modules.irrigation.service.processing import irrigation_service

logger = logging.getLogger(__name__)

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
    persisted = await irrigation_service.persist_upload(
        mission_id=mission_id,
        upload=image,
        timestamp_utc=parsed_timestamp,
    )
    try:
        meta_payload = json.loads(meta_data) if meta_data else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="meta_data must be valid JSON") from exc
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
    capture = await irrigation_application.save_capture(db, capture=capture)
    return CaptureRecordOut.model_validate(capture, from_attributes=True)


@router.get("/missions/{mission_id}/captures", response_model=list[CaptureRecordOut])
async def list_mission_captures(
    mission_id: str,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> list[CaptureRecordOut]:
    await _owned_mission_or_404(db, mission_id=mission_id, org_user=org_user)
    captures = await irrigation_service.list_captures(db, mission_id=mission_id)
    return [CaptureRecordOut.model_validate(item, from_attributes=True) for item in captures]


@router.post("/missions/{mission_id}/process", response_model=ProcessedFieldLayerOut)
async def process_irrigation_mission(
    mission_id: str,
    force: bool = False,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> ProcessedFieldLayerOut:
    mission = await _owned_mission_or_404(db, mission_id=mission_id, org_user=org_user)
    layer = await irrigation_service.process_mission(db, mission=mission, force=force)
    return ProcessedFieldLayerOut.model_validate(layer, from_attributes=True)


@router.get("/missions/{mission_id}/summary", response_model=IrrigationMissionSummaryOut)
async def get_irrigation_mission_summary(
    mission_id: str,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> IrrigationMissionSummaryOut:
    await _owned_mission_or_404(db, mission_id=mission_id, org_user=org_user)
    captures, layer, zones, points = await irrigation_application.summary_components(
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
