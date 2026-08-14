from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.modules.agriculture.models import (
    AgricultureFlight,
    AgricultureMediaManifest,
    AgricultureMediaQualityException,
    AgricultureUploadSession,
    new_id,
)
from backend.modules.agriculture.schemas import (
    FlightManifestIn,
    MediaManifestIn,
    MediaLifecycleIn,
    ResumableUploadIn,
)
from backend.modules.agriculture.service import agriculture_service
from backend.modules.agriculture.storage import agriculture_storage
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.observability.instruments import observed_span

from backend.modules.agriculture.routers import common as _common
from backend.modules.agriculture.routers.common import (
    AGRICULTURE_SCHEMA_VERSION,
)

router = APIRouter()


@router.post("/flights/{flight_id}/manifests", response_model=dict[str, Any])
async def ingest_flight_manifest(flight_id: str, payload: FlightManifestIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    flight = await db.scalar(select(AgricultureFlight).where(AgricultureFlight.id == flight.id).with_for_update())
    calculated = hashlib.sha256(json.dumps(payload.payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if calculated.lower() != payload.checksum.lower():
        raise HTTPException(status_code=422, detail={"code": "MANIFEST_CHECKSUM_MISMATCH", "message": "Manifest checksum does not match canonical JSON payload"})
    manifests = dict((flight.input_manifest or {}).get("manifests", {}))
    existing = manifests.get(payload.idempotency_key)
    if existing and existing["checksum"] != calculated:
        raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "Idempotency-Key was already used with another manifest"})
    record = existing or {"kind": payload.kind, "checksum": calculated, "payload": payload.payload, "ingested_at": datetime.now(UTC).isoformat()}
    manifests[payload.idempotency_key] = record
    flight.input_manifest = {**(flight.input_manifest or {}), "manifests": manifests}
    await db.commit()
    return {"schema_version": AGRICULTURE_SCHEMA_VERSION, "flight_id": flight.id, "idempotent_replay": existing is not None, **record}


@router.post("/flights/{flight_id}/media", response_model=dict[str, Any])
async def register_media(flight_id: str, payload: MediaManifestIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    await _common.enforce_rate_limit(key=f"agriculture:media:{org_user.user.id}:{flight_id}", limit=settings.agriculture_rate_media_per_window, window_seconds=settings.agriculture_rate_window_seconds)
    try:
        if not agriculture_storage.exists(payload.storage_key):
            raise ValueError("Agriculture media object is not present in configured storage")
        actual_checksum = agriculture_storage.checksum(payload.storage_key)
        if actual_checksum.lower() != payload.checksum.lower():
            raise ValueError("Agriculture media object checksum mismatch")
        detected = agriculture_storage.validate_file_content(payload.storage_key, declared_content_type=payload.content_type)
        scan = agriculture_storage.scan_file(payload.storage_key)
        if scan["status"] != "passed":
            raise ValueError("Agriculture media failed the malware safety gate")
        with observed_span("agriculture.media_register", flight_id=flight.id, field_id=flight.field_id, mission_id=flight.mission_id):
            manifest = await agriculture_service.register_media(db, flight=flight, values={
            "source_kind": payload.source_kind,
            "storage_key": payload.storage_key,
            "checksum": payload.checksum,
            "content_type": payload.content_type,
            "codec": payload.codec,
            "byte_size": payload.byte_size,
            "width": payload.width,
            "height": payload.height,
            "duration_seconds": payload.duration_seconds,
            "camera_serial": payload.camera_serial,
            "calibration_id": payload.calibration_id,
            "capture_start_utc": payload.capture_start,
            "capture_end_utc": payload.capture_end,
            "metadata_json": {**payload.metadata, "malware_scan": scan, "detected_content_type": detected},
            "security_status": "passed",
            "security_reason": scan["reason"],
            "security_checked_at": datetime.now(UTC),
            })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    flight.input_manifest = {**(flight.input_manifest or {}), "media_ids": [*(flight.input_manifest or {}).get("media_ids", []), manifest.id]}
    await db.commit()
    _common.emit_audit_event(event_name="agriculture_media_registered", action="create_media_manifest", resource_type="agriculture_media", result="success", actor_type="user", actor_id=str(getattr(org_user.user, "id", "")), resource_id=manifest.id, extra={"flight_id": flight.id, "source_kind": manifest.source_kind, "byte_size": manifest.byte_size})
    return {"id": manifest.id, "flight_id": flight.id, "source_kind": manifest.source_kind, "checksum": manifest.checksum, "signed_url": agriculture_storage.sign(manifest.storage_key)}


async def _owned_media(media_id: str, org_user: OrgUser, db: AsyncSession) -> AgricultureMediaManifest:
    row = await db.scalar(select(AgricultureMediaManifest).join(AgricultureFlight, AgricultureFlight.id == AgricultureMediaManifest.flight_id).where(
        AgricultureMediaManifest.id == media_id,
        AgricultureFlight.org_id == getattr(org_user.user, "org_id", None),
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Agriculture media not found")
    return row


def _media_lifecycle_status(media: AgricultureMediaManifest) -> dict[str, Any]:
    metadata = dict(media.metadata_json or {})
    return {
        "id": media.id,
        "flight_id": media.flight_id,
        "checksum": media.checksum,
        "content_type": media.content_type,
        "byte_size": media.byte_size,
        "storage_class": media.storage_class,
        "artifact_version": media.artifact_version,
        "storage_present": agriculture_storage.exists(media.storage_key),
        "security_status": media.security_status,
        "security_reason": media.security_reason,
        "security_checked_at": media.security_checked_at,
        "retention_status": media.retention_status,
        "retention_expires_at": media.retention_expires_at,
        "revoked_at": media.revoked_at,
        "backup_available": bool(metadata.get("backup_key")),
    }


@router.get("/media/{media_id}/status")
async def get_media_status(media_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    return _media_lifecycle_status(await _owned_media(media_id, org_user, db))


@router.post("/media/{media_id}/backup")
async def backup_media(media_id: str, payload: MediaLifecycleIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)):
    media = await _owned_media(media_id, org_user, db)
    tenant = str(getattr(org_user.user, "org_id", None) or "public")
    backup_key = f"org/{tenant}/{settings.agriculture_storage_backup_prefix.strip('/')}/{media.id}-v{media.artifact_version}-{media.checksum}"
    try:
        agriculture_storage.validate_tenant_key(backup_key, org_id=getattr(org_user.user, "org_id", None), resource=settings.agriculture_storage_backup_prefix)
        agriculture_storage.backup(media.storage_key, backup_key=backup_key)
    except (FileNotFoundError, ValueError, IOError) as exc:
        raise HTTPException(status_code=409, detail="Media backup could not be verified") from exc
    media.metadata_json = {**(media.metadata_json or {}), "backup_key": backup_key, "backup_checksum": media.checksum, "backup_created_at": datetime.now(UTC).isoformat(), "backup_reason": payload.reason}
    await db.commit()
    _common.emit_audit_event(event_name="agriculture_media_backed_up", action="backup", resource_type="agriculture_media", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=media.id, extra={"reason": payload.reason, "checksum": media.checksum})
    return _media_lifecycle_status(media) | {"status": "backed_up"}


@router.post("/media/{media_id}/revoke")
async def revoke_media(media_id: str, payload: MediaLifecycleIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)):
    media = await _owned_media(media_id, org_user, db)
    media.retention_status = "archived"
    media.revoked_at = datetime.now(UTC)
    media.metadata_json = {**(media.metadata_json or {}), "revocation_reason": payload.reason}
    await db.commit()
    _common.emit_audit_event(event_name="agriculture_media_revoked", action="revoke", resource_type="agriculture_media", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=media.id, extra={"reason": payload.reason})
    return _media_lifecycle_status(media)


@router.post("/media/{media_id}/restore")
async def restore_media(media_id: str, payload: MediaLifecycleIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_write)):
    media = await _owned_media(media_id, org_user, db)
    if media.security_status in {"quarantined", "rejected"}:
        raise HTTPException(status_code=409, detail="Security-quarantined media cannot be restored")
    metadata = dict(media.metadata_json or {})
    if not agriculture_storage.exists(media.storage_key) and metadata.get("backup_key"):
        try:
            agriculture_storage.restore(metadata["backup_key"], target_key=media.storage_key, expected_checksum=media.checksum)
        except (FileNotFoundError, ValueError, IOError) as exc:
            raise HTTPException(status_code=409, detail="Media backup restore failed checksum verification") from exc
    if not agriculture_storage.exists(media.storage_key):
        raise HTTPException(status_code=409, detail="No retained media artifact or verified backup is available")
    media.retention_status = "active"
    media.revoked_at = None
    media.metadata_json = {**metadata, "restore_reason": payload.reason, "restored_at": datetime.now(UTC).isoformat()}
    await db.commit()
    _common.emit_audit_event(event_name="agriculture_media_restored", action="restore", resource_type="agriculture_media", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=media.id, extra={"reason": payload.reason})
    return _media_lifecycle_status(media)


@router.post("/flights/{flight_id}/uploads", response_model=dict[str, Any], status_code=201)
async def initiate_upload(flight_id: str, payload: ResumableUploadIn, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    await _common.enforce_rate_limit(key=f"agriculture:upload-init:{org_user.user.id}:{flight_id}", limit=settings.agriculture_rate_media_per_window, window_seconds=settings.agriculture_rate_window_seconds)
    if payload.total_bytes > settings.agriculture_max_media_bytes:
        raise HTTPException(status_code=413, detail="Agriculture media exceeds configured quota")
    upload_id = new_id()
    tenant = str(flight.org_id) if flight.org_id is not None else "public"
    current_usage = agriculture_storage.usage_bytes(f"org/{tenant}")
    if current_usage + payload.total_bytes > settings.agriculture_org_storage_quota_bytes:
        raise HTTPException(status_code=413, detail={"code": "AGRICULTURE_STORAGE_QUOTA_EXCEEDED", "message": "Organization agriculture storage quota exceeded"})
    from backend.observability import prometheus_metrics
    prometheus_metrics.agriculture_storage_bytes.labels(tenant=tenant, backend=str(getattr(settings, "storage_backend", "local")).lower()).set(current_usage)
    suffix = Path(payload.filename or "").suffix.lower()
    suffix = suffix if suffix.startswith(".") and suffix[1:].isalnum() and len(suffix) <= 8 else ""
    storage_key = f"org/{tenant}/flights/{flight.id}/{upload_id}{suffix}"
    temporary_key = f"org/{tenant}/uploads/{upload_id}.part"
    agriculture_storage.validate_tenant_key(storage_key, org_id=flight.org_id, resource=f"flights/{flight.id}")
    agriculture_storage.validate_tenant_key(temporary_key, org_id=flight.org_id, resource="uploads")
    agriculture_storage.validate_content(content_type=payload.content_type, byte_size=payload.total_bytes, quota_bytes=settings.agriculture_max_media_bytes)
    now = datetime.now(UTC)
    session = AgricultureUploadSession(id=upload_id, flight_id=flight.id, org_id=flight.org_id, source_kind=payload.source_kind, storage_key=storage_key, temporary_key=temporary_key, filename=payload.filename, content_type=payload.content_type, total_bytes=payload.total_bytes, checksum=payload.checksum.lower(), metadata_json=payload.metadata, expires_at=now + timedelta(seconds=max(60, settings.agriculture_upload_session_ttl_seconds)))
    db.add(session)
    await db.commit()
    return {"id": session.id, "status": session.status, "upload_offset": 0, "total_bytes": session.total_bytes, "chunk_bytes": settings.agriculture_upload_chunk_bytes, "chunk_url": f"/agriculture/flights/{flight.id}/uploads/{session.id}/chunks", "complete_url": f"/agriculture/flights/{flight.id}/uploads/{session.id}/complete", "expires_at": session.expires_at}


@router.put("/flights/{flight_id}/uploads/{upload_id}/chunks", response_model=dict[str, Any])
async def upload_chunk(flight_id: str, upload_id: str, chunk: UploadFile = File(...), upload_offset: int = Header(0, alias="Upload-Offset", ge=0), db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    await _common.enforce_rate_limit(key=f"agriculture:upload-chunk:{org_user.user.id}:{flight_id}", limit=settings.agriculture_rate_media_per_window * 20, window_seconds=settings.agriculture_rate_window_seconds)
    session = await db.scalar(select(AgricultureUploadSession).where(AgricultureUploadSession.id == upload_id, AgricultureUploadSession.flight_id == flight.id).with_for_update())
    if session is None or session.status != "uploading":
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.expires_at <= datetime.now(UTC):
        session.status = "expired"
        await db.commit()
        raise HTTPException(status_code=410, detail="Upload session expired")
    data = await chunk.read(settings.agriculture_upload_chunk_bytes + 1)
    if len(data) > settings.agriculture_upload_chunk_bytes:
        raise HTTPException(status_code=413, detail="Upload chunk exceeds configured limit")
    if upload_offset > session.received_bytes or upload_offset + len(data) > session.total_bytes:
        raise HTTPException(status_code=409, detail=f"Upload offset mismatch: expected {session.received_bytes}")
    if upload_offset < session.received_bytes:
        if agriculture_storage.read_range(session.temporary_key, offset=upload_offset, length=len(data)) != data:
            raise HTTPException(status_code=409, detail="Chunk conflicts with already stored bytes")
        return {"id": session.id, "status": session.status, "upload_offset": session.received_bytes, "total_bytes": session.total_bytes, "chunk_url": f"/agriculture/flights/{flight.id}/uploads/{session.id}/chunks", "complete_url": f"/agriculture/flights/{flight.id}/uploads/{session.id}/complete", "expires_at": session.expires_at}
    session.received_bytes = agriculture_storage.write_chunk(session.temporary_key, data, offset=upload_offset)
    await db.commit()
    return {"id": session.id, "status": session.status, "upload_offset": session.received_bytes, "total_bytes": session.total_bytes, "chunk_url": f"/agriculture/flights/{flight.id}/uploads/{session.id}/chunks", "complete_url": f"/agriculture/flights/{flight.id}/uploads/{session.id}/complete", "expires_at": session.expires_at}


@router.post("/flights/{flight_id}/uploads/{upload_id}/complete", response_model=dict[str, Any])
async def complete_upload(flight_id: str, upload_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    session = await db.scalar(select(AgricultureUploadSession).where(AgricultureUploadSession.id == upload_id, AgricultureUploadSession.flight_id == flight.id).with_for_update())
    if session is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.status == "completed" and session.media_id:
        return {"id": session.media_id, "upload_id": session.id, "status": "completed"}
    if session.expires_at <= datetime.now(UTC):
        session.status = "expired"
        await db.commit()
        raise HTTPException(status_code=410, detail="Upload session expired")
    if session.received_bytes != session.total_bytes:
        raise HTTPException(status_code=409, detail=f"Upload incomplete: {session.received_bytes}/{session.total_bytes} bytes")
    actual_checksum = agriculture_storage.checksum(session.temporary_key)
    if actual_checksum.lower() != session.checksum.lower():
        session.status = "quarantined"
        session.metadata_json = {**(session.metadata_json or {}), "security_reason": "checksum_mismatch", "quarantined_at": datetime.now(UTC).isoformat()}
        db.add(AgricultureMediaQualityException(flight_id=flight.id, upload_id=session.id, code="CHECKSUM_MISMATCH", message="Uploaded bytes do not match the declared SHA-256 checksum", details={"expected": session.checksum, "actual": actual_checksum}))
        await db.commit()
        raise HTTPException(status_code=422, detail="Upload checksum does not match manifest")
    try:
        detected_content_type = agriculture_storage.validate_file_content(
            session.temporary_key,
            declared_content_type=session.content_type,
        )
    except ValueError as exc:
        session.status = "quarantined"
        session.metadata_json = {**(session.metadata_json or {}), "security_reason": "content_mismatch", "quarantined_at": datetime.now(UTC).isoformat()}
        db.add(AgricultureMediaQualityException(flight_id=flight.id, upload_id=session.id, code="CONTENT_MISMATCH", message="Uploaded bytes do not match the declared media content type", details={"content_type": session.content_type, "error": str(exc)}))
        await db.commit()
        raise HTTPException(status_code=422, detail={"code": "MEDIA_CONTENT_MISMATCH", "message": str(exc)}) from exc
    try:
        scan = agriculture_storage.scan_file(session.temporary_key)
    except RuntimeError as exc:
        session.status = "quarantined"
        session.metadata_json = {**(session.metadata_json or {}), "security_reason": "scanner_unavailable", "quarantined_at": datetime.now(UTC).isoformat()}
        db.add(AgricultureMediaQualityException(flight_id=flight.id, upload_id=session.id, code="MALWARE_SCAN_UNAVAILABLE", message="Media scanner is required but unavailable", details={"error": str(exc)}))
        await db.commit()
        raise HTTPException(status_code=503, detail={"code": "MALWARE_SCAN_UNAVAILABLE", "message": "Media was quarantined until the configured scanner is available"}) from exc
    if scan["status"] != "passed":
        session.status = "quarantined"
        session.metadata_json = {**(session.metadata_json or {}), "security_reason": scan["reason"], "scanner": scan["scanner"], "quarantined_at": datetime.now(UTC).isoformat()}
        db.add(AgricultureMediaQualityException(flight_id=flight.id, upload_id=session.id, code="MALWARE_DETECTED", message="Media was quarantined by the malware safety gate", details=scan))
        await db.commit()
        raise HTTPException(status_code=422, detail={"code": "MEDIA_QUARANTINED", "message": "Media failed the malware safety gate"})
    if session.content_type is None:
        session.content_type = detected_content_type
    agriculture_storage.move(session.temporary_key, session.storage_key)
    manifest = await agriculture_service.register_media(db, flight=flight, values={"source_kind": session.source_kind, "storage_key": session.storage_key, "checksum": actual_checksum, "content_type": session.content_type, "byte_size": session.total_bytes, "metadata_json": {**(session.metadata_json or {}), "malware_scan": scan}, "security_status": "passed", "security_reason": scan["reason"], "security_checked_at": datetime.now(UTC)})
    session.media_id = manifest.id
    session.status = "completed"
    session.completed_at = datetime.now(UTC)
    flight.input_manifest = {**(flight.input_manifest or {}), "media_ids": [*(flight.input_manifest or {}).get("media_ids", []), manifest.id]}
    await db.commit()
    _common.emit_audit_event(event_name="agriculture_upload_completed", action="complete", resource_type="agriculture_upload", result="success", actor_type="user", actor_id=str(org_user.user.id), resource_id=session.id, extra={"flight_id": flight.id, "media_id": manifest.id, "checksum": actual_checksum})
    return {"id": manifest.id, "upload_id": session.id, "status": "completed", "flight_id": flight.id, "checksum": actual_checksum, "signed_url": agriculture_storage.sign(manifest.storage_key)}


@router.post("/flights/{flight_id}/uploads/{upload_id}/retry", response_model=dict[str, Any])
async def retry_upload(flight_id: str, upload_id: str, db: AsyncSession = Depends(get_db), org_user: OrgUser = Depends(require_org_user)):
    flight = await _common._owned_flight(flight_id, org_user, db)
    session = await db.scalar(select(AgricultureUploadSession).where(AgricultureUploadSession.id == upload_id, AgricultureUploadSession.flight_id == flight.id).with_for_update())
    if session is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.status == "completed":
        return {"id": session.id, "status": session.status, "upload_offset": session.received_bytes, "total_bytes": session.total_bytes, "retryable": False}
    if session.status == "quarantined":
        raise HTTPException(status_code=409, detail={"code": "UPLOAD_QUARANTINED", "message": "Quarantined media must be uploaded as a new session after correcting the source file."})
    if not agriculture_storage.safe_path(session.temporary_key).exists():
        raise HTTPException(status_code=409, detail={"code": "UPLOAD_PART_MISSING", "message": "The resumable part is no longer available; start a new upload."})
    session.status = "uploading"
    session.expires_at = datetime.now(UTC) + timedelta(seconds=max(60, settings.agriculture_upload_session_ttl_seconds))
    await db.commit()
    return {"id": session.id, "status": session.status, "upload_offset": session.received_bytes, "total_bytes": session.total_bytes, "chunk_bytes": settings.agriculture_upload_chunk_bytes, "expires_at": session.expires_at, "retryable": True}

