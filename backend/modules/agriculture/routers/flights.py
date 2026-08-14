from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.agriculture.models import (
    AgricultureFrameLineage,
    AgricultureMediaManifest,
    AgricultureMediaQualityException,
    AgricultureTelemetrySample,
    AgricultureTimelineBookmark,
)
from backend.modules.agriculture.schemas import (
    AgricultureFlightOut,
)
from backend.modules.agriculture.storage import agriculture_storage
from backend.modules.identity.dependencies import OrgUser, require_org_user

from backend.modules.agriculture.routers import common as _common
from backend.modules.agriculture.routers.common import (
    AGRICULTURE_SCHEMA_VERSION,
)

router = APIRouter()


@router.get("/flights/{flight_id}", response_model=AgricultureFlightOut)
async def get_flight(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    return await _common._owned_flight(flight_id, org_user, db)


@router.get("/flights/{flight_id}/quality")
async def get_flight_quality(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    return {"flight_id": flight.id, "status": flight.status, "quality": flight.quality_summary or {"status": "pending"}}


@router.get("/flights/{flight_id}/coverage")
async def get_flight_coverage(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    return {"flight_id": flight.id, "coverage": flight.coverage_summary or {"status": "pending"}}


@router.get("/flights/{flight_id}/media-inventory")
async def get_media_inventory(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    return await _common._media_inventory(flight, db)


@router.post("/flights/{flight_id}/media-inventory/reconcile")
@router.post("/flights/{flight_id}/validate-media")
async def reconcile_media_inventory(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    snapshot = await _common._media_inventory(flight, db)
    findings = []
    for media_id in snapshot["missing_manifest_ids"]:
        findings.append(("MISSING_MANIFEST", "Expected capture is not registered", {"media_id": media_id}, None, None))
    for media_id in snapshot["storage_missing_media_ids"]:
        findings.append(("STORAGE_MISSING", "Registered media object is missing from storage", {"media_id": media_id}, media_id, None))
    for upload_id in snapshot["active_upload_ids"]:
        findings.append(("UPLOAD_INCOMPLETE", "Upload has not reached its declared byte size", {"upload_id": upload_id}, None, upload_id))
    for upload_id in snapshot["quarantined_upload_ids"]:
        findings.append(("UPLOAD_QUARANTINED", "Upload failed checksum or content validation", {"upload_id": upload_id}, None, upload_id))
    for code, message, details, media_id, upload_id in findings:
        existing = await db.scalar(select(AgricultureMediaQualityException).where(AgricultureMediaQualityException.flight_id == flight.id, AgricultureMediaQualityException.code == code, AgricultureMediaQualityException.status == "open", AgricultureMediaQualityException.media_id == media_id, AgricultureMediaQualityException.upload_id == upload_id))
        if existing is None:
            db.add(AgricultureMediaQualityException(flight_id=flight.id, media_id=media_id, upload_id=upload_id, code=code, message=message, details=details))
    if findings:
        await db.commit()
    return await _common._media_inventory(flight, db)


@router.get("/flights/{flight_id}/media-timeline")
async def get_media_timeline(flight_id: str, limit: int = Query(500, ge=1, le=2000), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    frames = list((await db.scalars(select(AgricultureFrameLineage).where(AgricultureFrameLineage.flight_id == flight.id).order_by(AgricultureFrameLineage.timestamp_utc.asc()).limit(limit))).all())
    media_ids = {row.media_id for row in frames if row.media_id}
    media_rows = list((await db.scalars(select(AgricultureMediaManifest).where(AgricultureMediaManifest.flight_id == flight.id, AgricultureMediaManifest.id.in_(media_ids), AgricultureMediaManifest.retention_status == "active"))).all()) if media_ids else []
    media_by_id = {row.id: row for row in media_rows}
    return {
        "schema_version": AGRICULTURE_SCHEMA_VERSION,
        "flight_id": flight.id,
        "frames": [
            {"id": row.id, "frame_index": row.frame_index, "timestamp_utc": row.timestamp_utc, "media_id": row.media_id, "signed_url": agriculture_storage.sign(media_by_id[row.media_id].storage_key) if row.media_id in media_by_id else None, "content_type": media_by_id[row.media_id].content_type if row.media_id in media_by_id else None, "footprint_geojson": row.footprint_geojson, "gsd_cm": row.gsd_cm, "quality_metrics": row.quality_metrics or {}, "telemetry_sample_before_id": row.telemetry_sample_before_id, "telemetry_sample_after_id": row.telemetry_sample_after_id}
            for row in frames
        ],
        "total": len(frames),
        "truncated": len(frames) >= limit,
    }


@router.get("/flights/{flight_id}/telemetry-window")
async def get_telemetry_window(flight_id: str, timestamp_utc: datetime | None = Query(default=None), window_seconds: float = Query(15.0, ge=1, le=120), limit: int = Query(200, ge=1, le=1000), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    query = select(AgricultureTelemetrySample).where(AgricultureTelemetrySample.flight_id == flight.id)
    if timestamp_utc is not None:
        center = timestamp_utc.astimezone(UTC) if timestamp_utc.tzinfo else timestamp_utc.replace(tzinfo=UTC)
        query = query.where(AgricultureTelemetrySample.timestamp_utc >= center - timedelta(seconds=window_seconds), AgricultureTelemetrySample.timestamp_utc <= center + timedelta(seconds=window_seconds))
    rows = list((await db.scalars(query.order_by(AgricultureTelemetrySample.timestamp_utc.asc()).limit(limit))).all())
    return {"schema_version": AGRICULTURE_SCHEMA_VERSION, "flight_id": flight.id, "center_timestamp_utc": timestamp_utc, "window_seconds": window_seconds, "samples": [{"id": row.id, "timestamp_utc": row.timestamp_utc, "lat": row.lat, "lon": row.lon, "relative_altitude_m": row.relative_altitude_m, "absolute_altitude_m": row.absolute_altitude_m, "ground_speed_mps": row.ground_speed_mps, "gps_quality": row.gps_quality, "yaw_deg": row.yaw_deg, "camera_trigger": row.camera_trigger, "source": row.source} for row in rows]}


@router.get("/flights/{flight_id}/timeline/bookmarks")
async def list_timeline_bookmarks(flight_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    rows = list((await db.scalars(select(AgricultureTimelineBookmark).where(AgricultureTimelineBookmark.flight_id == flight.id, AgricultureTimelineBookmark.created_by_user_id == org_user.user.id).order_by(AgricultureTimelineBookmark.created_at.asc()))).all())
    return {"flight_id": flight.id, "bookmarks": [{"id": row.id, "frame_lineage_id": row.frame_lineage_id, "note": row.note, "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]}


@router.post("/flights/{flight_id}/timeline/bookmarks", status_code=201)
async def create_timeline_bookmark(flight_id: str, payload: dict[str, Any], db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    frame_id = str(payload.get("frame_lineage_id", ""))
    note = str(payload.get("note", "")).strip()[:1000] or None
    frame = await db.scalar(select(AgricultureFrameLineage).where(AgricultureFrameLineage.id == frame_id, AgricultureFrameLineage.flight_id == flight.id))
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame lineage not found for flight")
    row = await db.scalar(select(AgricultureTimelineBookmark).where(AgricultureTimelineBookmark.flight_id == flight.id, AgricultureTimelineBookmark.frame_lineage_id == frame.id, AgricultureTimelineBookmark.created_by_user_id == org_user.user.id).with_for_update())
    if row is None:
        row = AgricultureTimelineBookmark(flight_id=flight.id, frame_lineage_id=frame.id, created_by_user_id=org_user.user.id, note=note)
        db.add(row)
    else:
        row.note = note
    await db.commit(); await db.refresh(row)
    return {"id": row.id, "flight_id": flight.id, "frame_lineage_id": row.frame_lineage_id, "note": row.note, "created_at": row.created_at, "updated_at": row.updated_at}


@router.delete("/flights/{flight_id}/timeline/bookmarks/{bookmark_id}", status_code=204)
async def delete_timeline_bookmark(flight_id: str, bookmark_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    row = await db.scalar(select(AgricultureTimelineBookmark).where(AgricultureTimelineBookmark.id == bookmark_id, AgricultureTimelineBookmark.flight_id == flight.id, AgricultureTimelineBookmark.created_by_user_id == org_user.user.id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Timeline bookmark not found")
    await db.delete(row); await db.commit()

