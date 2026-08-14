from __future__ import annotations

from collections import OrderedDict
from time import monotonic
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.core.rate_limit import enforce_rate_limit as enforce_rate_limit
from backend.modules.agriculture.models import (
    AgricultureFlight,
    AgricultureFrameLineage,
    AgricultureMediaManifest,
    AgricultureMediaQualityException,
    AgricultureUploadSession,
)
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.schemas import (
    AgricultureFieldProfileOut,
    AgriculturePlanOut,
    AgriculturePreflightOut,
)
from backend.modules.agriculture.storage import agriculture_storage
from backend.modules.agriculture.live import LiveAgricultureProcessor as LiveAgricultureProcessor
from backend.modules.agriculture.live import decode_rgb_frame as decode_rgb_frame
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.fields.service import field_service
from backend.modules.agriculture.workflow_models import (
    AgricultureMissionPlan,
    AgriculturePreflightSnapshot,
)
from backend.observability.audit import emit_audit_event as emit_audit_event
from backend.observability import prometheus_metrics

AGRICULTURE_SCHEMA_VERSION = "agriculture.v1"


_LIVE_PROCESSOR_MAX = 64
_LIVE_PROCESSOR_TTL_S = 30 * 60
_live_processors: OrderedDict[str, tuple[LiveAgricultureProcessor, float]] = OrderedDict()


def _evict_live_processors(now: float | None = None) -> None:
    current = monotonic() if now is None else now
    expired = [key for key, (_, stamped) in list(_live_processors.items()) if current - stamped > _LIVE_PROCESSOR_TTL_S]
    for key in expired:
        _live_processors.pop(key, None)
    while len(_live_processors) > _LIVE_PROCESSOR_MAX:
        _live_processors.popitem(last=False)
    prometheus_metrics.agriculture_live_processors.set(len(_live_processors))


def get_live_processor(flight_id: str) -> LiveAgricultureProcessor:
    """Return a per-flight live processor, evicting by TTL and max size."""
    now = monotonic()
    _evict_live_processors(now)
    entry = _live_processors.get(flight_id)
    if entry is not None:
        processor, _ = entry
        _live_processors.move_to_end(flight_id)
        _live_processors[flight_id] = (processor, now)
        return processor
    processor = LiveAgricultureProcessor(max_queue=8, sampler_hz=3.0)
    _live_processors[flight_id] = (processor, now)
    _evict_live_processors(now)
    return processor


def _profile_out(profile) -> AgricultureFieldProfileOut:
    return AgricultureFieldProfileOut(
        id=profile.id,
        field_id=profile.field_id,
        crop_type=profile.crop_type,
        variety=profile.variety,
        season=profile.season,
        planting_date=profile.planting_date,
        growth_stage=profile.growth_stage,
        row_direction_deg=profile.row_direction_deg,
        expected_row_spacing_m=profile.expected_row_spacing_m,
        expected_plant_spacing_m=profile.expected_plant_spacing_m,
        stand_gap_multiplier=profile.stand_gap_multiplier,
        weed_density_cell_m=profile.weed_density_cell_m,
        weed_hotspot_percentile=profile.weed_hotspot_percentile,
        soil_type=profile.soil_type,
        irrigation_method=profile.irrigation_method,
        management_zone=profile.management_zone,
        timezone=profile.timezone,
        notes=profile.notes,
        metadata=profile.metadata_json or {},
    )


def _plan_out(plan: AgricultureMissionPlan) -> AgriculturePlanOut:
    return AgriculturePlanOut(
        id=plan.id,
        field_id=plan.field_id,
        status=plan.status,
        plan_hash=plan.plan_hash,
        payload=plan.payload_json or {},
        route_geojson=plan.route_geojson or {},
        estimates=plan.estimates_json or {},
        warnings=plan.warnings_json or [],
        validation_errors=plan.validation_errors_json or [],
        created_at=plan.created_at,
        grid_revision=plan.grid_revision,
        planner_version=plan.planner_version,
    )


def _preflight_out(snapshot: AgriculturePreflightSnapshot) -> AgriculturePreflightOut:
    return AgriculturePreflightOut(
        id=snapshot.id,
        plan_id=snapshot.plan_id,
        status=snapshot.status,
        checks=snapshot.checks_json or [],
        acknowledged=snapshot.acknowledged_at is not None,
        expires_at=snapshot.expires_at,
        evaluated_at=snapshot.created_at,
        evaluator_version=snapshot.evaluator_version,
        signoff_hash=snapshot.signoff_hash,
        operator_notes=snapshot.operator_notes,
    )


async def _owned_field(field_id: int, org_user: OrgUser, db: AsyncSession):
    field = await field_service.get_owned(db, field_id=field_id, user=org_user.user)
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


async def _owned_flight(flight_id: str, org_user: OrgUser, db: AsyncSession) -> AgricultureFlight:
    flight = await agriculture_repository.get_flight(db, flight_id=flight_id, user=org_user.user)
    if flight is None:
        raise HTTPException(status_code=404, detail="Agriculture flight not found")
    return flight


async def require_owned_flight(
    flight_id: str,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> AgricultureFlight:
    """FastAPI dependency: resolve and authorize an agriculture flight by path id."""
    return await _owned_flight(flight_id, org_user, db)


def agriculture_rate_limit(
    scope: str,
    *,
    limit: int | None = None,
    settings_limit: str | None = None,
):
    """FastAPI dependency factory for per-user/flight agriculture rate limits."""

    async def _dep(
        flight_id: str,
        org_user: OrgUser = Depends(require_org_user),
    ) -> None:
        resolved_limit = limit
        if resolved_limit is None:
            if settings_limit is None:
                raise ValueError("agriculture_rate_limit requires limit or settings_limit")
            resolved_limit = int(getattr(settings, settings_limit))
        await enforce_rate_limit(
            key=f"agriculture:{scope}:{org_user.user.id}:{flight_id}",
            limit=resolved_limit,
            window_seconds=settings.agriculture_rate_window_seconds,
        )

    return _dep


async def _media_inventory(flight: AgricultureFlight, db: AsyncSession) -> dict[str, Any]:
    manifests = list((await db.scalars(select(AgricultureMediaManifest).where(AgricultureMediaManifest.flight_id == flight.id).order_by(AgricultureMediaManifest.created_at.asc()))).all())
    uploads = list((await db.scalars(select(AgricultureUploadSession).where(AgricultureUploadSession.flight_id == flight.id).order_by(AgricultureUploadSession.created_at.asc()))).all())
    exceptions = list((await db.scalars(select(AgricultureMediaQualityException).where(AgricultureMediaQualityException.flight_id == flight.id, AgricultureMediaQualityException.status == "open").order_by(AgricultureMediaQualityException.created_at.desc()))).all())
    registered_ids = {manifest.id for manifest in manifests}
    expected_ids = set((flight.input_manifest or {}).get("media_ids", []))
    missing_ids = sorted(expected_ids - registered_ids)
    storage_missing = [manifest.id for manifest in manifests if not agriculture_storage.exists(manifest.storage_key)]
    quarantined_media = [manifest.id for manifest in manifests if manifest.security_status in {"quarantined", "rejected"}]
    active_uploads = [item.id for item in uploads if item.status == "uploading"]
    quarantined_uploads = [item.id for item in uploads if item.status == "quarantined"]
    processed_frames = int(await db.scalar(select(func.count()).select_from(AgricultureFrameLineage).where(AgricultureFrameLineage.flight_id == flight.id)) or 0)
    ready = bool(manifests) and not missing_ids and not storage_missing and not quarantined_media and not active_uploads and not quarantined_uploads and not exceptions
    tenant = str(flight.org_id) if flight.org_id is not None else "public"
    usage = agriculture_storage.usage_bytes(f"org/{tenant}")
    return {
        "schema_version": AGRICULTURE_SCHEMA_VERSION,
        "flight_id": flight.id,
        "status": flight.status,
        "registered": len(manifests),
        "expected": len(expected_ids),
        "missing_manifest_ids": missing_ids,
        "storage_missing_media_ids": storage_missing,
        "quarantined_media_ids": quarantined_media,
        "active_upload_ids": active_uploads,
        "quarantined_upload_ids": quarantined_uploads,
        "processed_frame_count": processed_frames,
        "open_exception_count": len(exceptions),
        "storage_usage_bytes": usage,
        "storage_quota_bytes": settings.agriculture_org_storage_quota_bytes,
        "ready_for_processing": ready,
        "manifests": [{"id": item.id, "source_kind": item.source_kind, "checksum": item.checksum, "content_type": item.content_type, "byte_size": item.byte_size, "retention_status": item.retention_status, "storage_class": item.storage_class, "artifact_version": item.artifact_version, "retention_expires_at": item.retention_expires_at, "revoked_at": item.revoked_at, "security_status": item.security_status, "security_reason": item.security_reason, "security_checked_at": item.security_checked_at, "storage_present": item.id not in storage_missing} for item in manifests],
        "uploads": [{"id": item.id, "status": item.status, "received_bytes": item.received_bytes, "total_bytes": item.total_bytes, "expires_at": item.expires_at, "security_reason": (item.metadata_json or {}).get("security_reason")} for item in uploads],
        "exceptions": [{"id": item.id, "code": item.code, "severity": item.severity, "message": item.message, "media_id": item.media_id, "upload_id": item.upload_id, "details": item.details, "created_at": item.created_at} for item in exceptions],
    }


def _parse_spatial_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    try:
        result = tuple(float(item) for item in value.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="bbox must be min_lon,min_lat,max_lon,max_lat") from exc
    if len(result) != 4 or result[0] >= result[2] or result[1] >= result[3] or result[0] < -180 or result[2] > 180 or result[1] < -90 or result[3] > 90:
        raise HTTPException(status_code=422, detail="bbox must be a valid EPSG:4326 extent")
    return result
