"""Asynchronous agriculture export endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.modules.agriculture.lifecycle import append_analysis_event
from backend.modules.agriculture.p5_models import (
    AgricultureExportAccessAudit,
    AgricultureExportJob,
)
from backend.modules.agriculture.p5_service import agriculture_safety_service
from backend.modules.agriculture.queue import (
    AgricultureAnalysisQueueError,
    agriculture_analysis_queue,
)
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.routers import common as _common
from backend.modules.agriculture.schemas import ExportIn, ExportOut
from backend.modules.agriculture.stage_operations import stage_input_checksum
from backend.modules.identity.dependencies import OrgUser, require_org_user

router = APIRouter()


@router.post("/analysis-runs/{run_id}/exports", response_model=ExportOut, status_code=202)
async def create_agriculture_export(
    run_id: str,
    payload: ExportIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    count = (
        select(func.count())
        .select_from(AgricultureExportJob)
        .where(AgricultureExportJob.created_at >= day_start)
    )
    count = (
        count.where(AgricultureExportJob.org_id == flight.org_id)
        if flight.org_id is not None
        else count.where(AgricultureExportJob.org_id.is_(None))
    )
    if int(await db.scalar(count) or 0) >= settings.agriculture_max_exports_per_org_per_day:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "AGRICULTURE_EXPORT_QUOTA_EXCEEDED",
                "message": "Organization daily export quota exceeded",
            },
        )
    await _common.enforce_rate_limit(
        key=f"agriculture:exports:{org_user.user.id}:{run_id}",
        limit=settings.agriculture_rate_analysis_runs_per_window,
        window_seconds=settings.agriculture_rate_window_seconds,
    )
    export = AgricultureExportJob(
        org_id=flight.org_id,
        field_id=flight.field_id,
        flight_id=flight.id,
        run_id=run.id,
        artifact_kind=payload.artifact_kind,
        format=payload.format,
        status="queued",
        source_manifest={
            "request": payload.model_dump(),
            "stage_version": "agriculture-export.v2",
        },
        requested_by_user_id=getattr(org_user.user, "id", None),
    )
    db.add(export)
    await db.flush()
    checksum = stage_input_checksum(
        run,
        "exports",
        extra={"export_id": export.id, "request": payload.model_dump()},
    )
    await append_analysis_event(
        db,
        run=run,
        flight=flight,
        event_type="export.queued",
        payload={
            "export_id": export.id,
            "format": export.format,
            "artifact_kind": export.artifact_kind,
        },
        dedupe_key=f"analysis:{run.id}:export:{export.id}:queued",
    )
    await db.commit()
    try:
        agriculture_analysis_queue.enqueue_stage(
            stage="exports",
            run_id=run.id,
            input_checksum=checksum,
            export_id=export.id,
        )
    except AgricultureAnalysisQueueError as exc:
        export.status = "failed"
        export.error = str(exc)
        await db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await db.refresh(export)
    return export


@router.get("/analysis-runs/{run_id}/exports", response_model=list[ExportOut])
async def list_agriculture_exports(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    return list(
        (
            await db.scalars(
                select(AgricultureExportJob)
                .where(AgricultureExportJob.run_id == run.id)
                .order_by(AgricultureExportJob.created_at.desc())
            )
        ).all()
    )


async def _owned_export(export_id: str, db, user) -> AgricultureExportJob:
    export = await db.get(AgricultureExportJob, export_id)
    org_id = getattr(user, "org_id", None)
    visible = export is not None and (
        export.org_id == org_id
        if org_id is not None
        else export.org_id is None and export.requested_by_user_id == user.id
    )
    if not visible:
        raise HTTPException(status_code=404, detail="Agriculture export not found")
    assert export is not None
    return export


@router.get("/exports/{export_id}", response_model=ExportOut)
async def get_agriculture_export(
    export_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    return await _owned_export(export_id, db, org_user.user)


@router.get("/exports/{export_id}/download")
async def download_agriculture_export(
    export_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    export = await _owned_export(export_id, db, org_user.user)
    try:
        return await agriculture_safety_service.access_export(
            db,
            job=export,
            user_id=getattr(org_user.user, "id", None),
            metadata={"user_agent": "agriculture-ui"},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=410 if str(exc) == "export_expired" else 422,
            detail=str(exc),
        ) from exc


@router.get("/exports/{export_id}/audit", response_model=list[dict[str, Any]])
async def agriculture_export_audit(
    export_id: str,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    export = await _owned_export(export_id, db, org_user.user)
    return list(
        (
            await db.scalars(
                select(AgricultureExportAccessAudit)
                .where(AgricultureExportAccessAudit.export_id == export.id)
                .order_by(AgricultureExportAccessAudit.created_at.asc())
            )
        ).all()
    )
