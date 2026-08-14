from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_write
from backend.modules.mapping.api.mapping_route_schemas import (
    MappingArtifactsIn,
    MappingJobStatusOut,
)
from backend.modules.mapping.api.mapping_route_support import (
    auto_generated_field_name,
    create_field_from_ring,
    create_upload_staging_dir,
    enqueue_job_or_503,
    mapping_inputs_root,
    move_staged_uploads_into_job,
    parse_form_object,
    persist_upload_files,
    relative_input_paths,
    to_job_status,
)
from backend.modules.mapping.application import mapping_application
from backend.modules.mapping.service.field_derivation import (
    collect_image_gps_locations,
    derive_field_ring_from_points,
)

router = APIRouter(tags=["mapping"])


@router.post("/jobs/upload", response_model=MappingJobStatusOut)
async def create_mapping_job_from_uploaded_images(
    files: list[UploadFile] = File(...),
    field_name: str | None = Form(default=None),
    processor: str = Form(default="webodm"),
    artifacts: str = Form(default=""),
    webodm_options: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> MappingJobStatusOut:
    user = org_user.user
    if processor.strip().lower() != "webodm":
        raise HTTPException(
            status_code=400, detail="Only processor='webodm' is currently supported."
        )

    inputs_root = mapping_inputs_root()
    stage_dir = create_upload_staging_dir(inputs_root)

    try:
        staged_paths = await persist_upload_files(files, destination_dir=stage_dir)
        gps_points = collect_image_gps_locations(staged_paths)
        derived_ring = derive_field_ring_from_points(gps_points)
        if not derived_ring:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Uploaded images do not contain usable GPS coordinates. "
                    "Select/draw a field first or upload geotagged drone images."
                ),
            )

        resolved_field_name = (field_name or "").strip() or auto_generated_field_name()
        artifacts_payload = MappingArtifactsIn.model_validate(
            parse_form_object(artifacts, field_name="artifacts")
        )
        webodm_options_payload = parse_form_object(
            webodm_options,
            field_name="webodm_options",
        )

        field = await create_field_from_ring(
            db,
            user=user,
            name=resolved_field_name,
            ring=derived_ring,
        )
        _model_id, job = await mapping_application.create_uncommitted_job(
            db, field=field, processor=processor.strip().lower(), status="uploading"
        )

        stored_paths = move_staged_uploads_into_job(
            staged_paths,
            inputs_root=inputs_root,
            job_id=job.id,
        )
        relative_paths = relative_input_paths(stored_paths, inputs_root=inputs_root)
        await mapping_application.save_upload_params(
            db,
            job=job,
            params={
                "field_id": field.id,
                "processor": job.processor,
                "input_source": "upload",
                "start_immediately": True,
                "artifacts": artifacts_payload.model_dump(),
                "webodm_options": webodm_options_payload,
                "uploaded_images": relative_paths,
                "uploaded_count": len(relative_paths),
                "auto_created_field": True,
                "field_source": {
                    "type": "image_gps",
                    "gps_point_count": len(gps_points),
                },
            },
        )

        await enqueue_job_or_503(db, job=job)
        await mapping_application.refresh(db, job=job)
        return to_job_status(job, [])
    except Exception:
        await mapping_application.rollback(db)
        raise
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
