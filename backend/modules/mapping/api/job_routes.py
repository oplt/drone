from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.mapping.api.mapping_route_schemas import (
    MappingJobCreateIn,
    MappingJobCreateOut,
    MappingJobDeleteOut,
    MappingJobStatusOut,
    MappingJobUploadOut,
)
from backend.modules.mapping.api.mapping_route_support import (
    assets_for_model,
    enqueue_job_or_503,
    get_owned_job_or_404,
    latest_photogrammetry_source_dir,
    mapping_inputs_root,
    persist_upload_files,
    relative_input_paths,
    to_job_status,
)
from backend.modules.mapping.application import mapping_application

logger = logging.getLogger(__name__)
router = APIRouter(tags=["mapping"])


@router.post("/jobs", response_model=MappingJobCreateOut)
async def create_mapping_job(
    payload: MappingJobCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> MappingJobCreateOut:
    user = org_user.user
    field = await mapping_application.get_field(db, field_id=payload.field_id, user=user)
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    params = payload.model_dump()
    if params.get("input_source") == "drone_sync":
        drone_sync = params.get("drone_sync")
        if not isinstance(drone_sync, dict):
            drone_sync = {}
        source_dir = drone_sync.get("source_dir")
        if not isinstance(source_dir, str) or not source_dir.strip():
            inferred = await latest_photogrammetry_source_dir(db)
            if inferred:
                drone_sync["source_dir"] = inferred
                params["drone_sync"] = drone_sync
                logger.info("Auto-filled mapping source_dir from latest flight: %s", inferred)

    model_id, job = await mapping_application.create_job(
        db, field=field, processor=payload.processor, params=params
    )

    if payload.start_immediately:
        await enqueue_job_or_503(db, job=job)
        await mapping_application.refresh(db, job=job)

    return MappingJobCreateOut(
        job_id=job.id,
        field_id=field.id,
        model_id=model_id,
        status=job.status,
        processor=job.processor,
    )


@router.get("/jobs", response_model=list[MappingJobStatusOut])
async def list_mapping_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[MappingJobStatusOut]:
    rows = await mapping_application.list_jobs_with_assets(
        db, user=org_user.user, limit=limit
    )
    return [to_job_status(job, assets) for job, assets in rows]


@router.get("/jobs/{job_id}", response_model=MappingJobStatusOut)
async def get_mapping_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> MappingJobStatusOut:
    job = await get_owned_job_or_404(db, job_id=job_id, user=org_user.user)
    assets = await assets_for_model(db, model_id=job.model_id)
    return to_job_status(job, assets)


@router.post("/jobs/{job_id}/start", response_model=MappingJobStatusOut)
async def start_mapping_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> MappingJobStatusOut:
    job = await get_owned_job_or_404(db, job_id=job_id, user=org_user.user)
    if job.status in {"processing", "ready"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start job in status '{job.status}'",
        )

    await enqueue_job_or_503(db, job=job)
    await mapping_application.refresh(db, job=job)
    assets = await assets_for_model(db, model_id=job.model_id)
    return to_job_status(job, assets)


@router.post("/jobs/{job_id}/images", response_model=MappingJobUploadOut)
async def upload_mapping_job_images(
    job_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> MappingJobUploadOut:
    job = await get_owned_job_or_404(db, job_id=job_id, user=org_user.user)
    if job.status not in {"pending", "uploading", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot upload inputs while job is '{job.status}'",
        )

    inputs_root = mapping_inputs_root()
    job_dir = inputs_root / str(job.id)
    stored_paths = await persist_upload_files(files, destination_dir=job_dir)
    uploaded_paths = relative_input_paths(stored_paths, inputs_root=inputs_root)
    await mapping_application.append_uploads(db, job=job, uploaded_paths=uploaded_paths)

    return MappingJobUploadOut(
        job_id=job.id,
        uploaded_count=len(uploaded_paths),
        uploaded_paths=uploaded_paths,
    )


@router.delete("/jobs/{job_id}", response_model=MappingJobDeleteOut)
async def delete_mapping_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> MappingJobDeleteOut:
    job = await get_owned_job_or_404(db, job_id=job_id, user=org_user.user)
    if job.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a mapping job while processing is active.",
        )

    await mapping_application.delete_job(db, job=job)
    shutil.rmtree(mapping_inputs_root() / str(job_id), ignore_errors=True)
    return MappingJobDeleteOut(job_id=job_id, deleted=True)
