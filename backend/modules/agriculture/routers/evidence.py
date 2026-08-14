"""Traceable observation evidence and source-video lineage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.agriculture.models import (
    AgricultureFrameLineage,
    AgricultureMediaManifest,
    AgricultureObservationEvidence,
)
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.routers import common as _common
from backend.modules.agriculture.storage import agriculture_storage
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.video_analysis.contracts import video_analysis_port

router = APIRouter()


@router.get("/observations/{observation_id}/evidence")
async def observation_evidence(
    observation_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    observation = await agriculture_repository.get_observation(
        db, observation_id=observation_id, user=org_user.user
    )
    if observation is None:
        raise HTTPException(status_code=404, detail="Agriculture observation not found")
    evidence_ids = [str(value) for value in (observation.evidence_ids or [])]
    if not evidence_ids:
        return {
            "observation_id": observation.id,
            "evidence_ids": [],
            "assets": [],
            "geometry": observation.geometry_geojson,
            "georef_status": observation.georef_status,
        }

    canonical_rows = list(
        (
            await db.scalars(
                select(AgricultureObservationEvidence).where(
                    AgricultureObservationEvidence.observation_id == observation.id
                )
            )
        ).all()
    )
    canonical_media_ids = {row.media_id for row in canonical_rows if row.media_id}
    media_rows = list(
        (
            await db.scalars(
                select(AgricultureMediaManifest).where(
                    AgricultureMediaManifest.flight_id == observation.flight_id,
                    AgricultureMediaManifest.id.in_([*evidence_ids, *canonical_media_ids]),
                    AgricultureMediaManifest.retention_status == "active",
                )
            )
        ).all()
    )
    frame_rows = list(
        (
            await db.scalars(
                select(AgricultureFrameLineage).where(
                    AgricultureFrameLineage.flight_id == observation.flight_id,
                    AgricultureFrameLineage.id.in_(evidence_ids),
                )
            )
        ).all()
    )
    frame_media_ids = {row.media_id for row in frame_rows}
    frame_media_rows = (
        list(
            (
                await db.scalars(
                    select(AgricultureMediaManifest).where(
                        AgricultureMediaManifest.flight_id == observation.flight_id,
                        AgricultureMediaManifest.id.in_(frame_media_ids),
                        AgricultureMediaManifest.retention_status == "active",
                    )
                )
            ).all()
        )
        if frame_media_ids
        else []
    )
    media_by_id = {row.id: row for row in [*media_rows, *frame_media_rows]}
    frame_to_media = {row.id: row.media_id for row in frame_rows}
    canonical_by_id = {str(row.detection_id): row for row in canonical_rows if row.detection_id}
    visible_video_ids: set[str] = set()
    for source_video_id in {row.source_video_id for row in canonical_rows if row.source_video_id}:
        if await video_analysis_port.get_source_for_user(db, source_video_id, org_user.user):
            visible_video_ids.add(source_video_id)
    assets = []
    for evidence_id in evidence_ids:
        media = media_by_id.get(evidence_id) or media_by_id.get(frame_to_media.get(evidence_id, ""))
        canonical = canonical_by_id.get(evidence_id)
        if media is None and canonical is not None and canonical.media_id:
            media = media_by_id.get(canonical.media_id)
        if media is None or media.retention_status != "active":
            continue
        assets.append(
            {
                "evidence_id": evidence_id,
                "media_id": media.id,
                "source_kind": media.source_kind,
                "content_type": media.content_type,
                "checksum": media.checksum,
                "signed_url": agriculture_storage.sign(media.storage_key),
                "frame_index": canonical.frame_index if canonical else None,
                "timestamp_seconds": canonical.timestamp_seconds if canonical else None,
                "timestamp_source": "canonical_video_detection"
                if canonical and canonical.timestamp_seconds is not None
                else None,
                "source_video_id": canonical.source_video_id
                if canonical and canonical.source_video_id in visible_video_ids
                else None,
            }
        )
    _common.emit_audit_event(
        event_name="agriculture_evidence_accessed",
        action="read_evidence",
        resource_type="agriculture_observation",
        result="success",
        actor_type="user",
        actor_id=str(getattr(org_user.user, "id", "")),
        resource_id=observation.id,
        extra={"flight_id": observation.flight_id, "asset_count": len(assets)},
    )
    return {
        "observation_id": observation.id,
        "evidence_ids": evidence_ids,
        "assets": assets,
        "geometry": observation.geometry_geojson,
        "georef_status": observation.georef_status,
    }
