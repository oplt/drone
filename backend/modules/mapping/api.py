from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.modules.fields.models import Field as FieldEntity
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.mapping.application import mapping_application
from backend.modules.mapping.models import Asset, MappingJob
from backend.modules.mapping.service.asset_gateway import AssetGatewayService
from backend.modules.mapping.service.field_derivation import (
    collect_image_gps_locations,
    derive_field_ring_from_points,
)
from backend.modules.mapping.service.queue import MappingJobQueue, MappingJobQueueError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mapping", tags=["mapping"])


def _asset_gateway() -> AssetGatewayService:
    return AssetGatewayService()


def _job_queue() -> MappingJobQueue:
    return MappingJobQueue()


class MappingArtifactsIn(BaseModel):
    orthomosaic: bool = True
    dsm: bool = True
    dtm: bool = False
    textured_mesh: bool = True
    point_cloud: bool = False
    xyz_tiles: bool = True


class MappingDroneSyncIn(BaseModel):
    source_dir: str | None = None
    recursive: bool = True


class MappingJobCreateIn(BaseModel):
    field_id: int
    processor: str = "webodm"
    input_source: Literal["upload", "drone_sync"] = "upload"
    drone_sync: MappingDroneSyncIn | None = None
    artifacts: MappingArtifactsIn = Field(default_factory=MappingArtifactsIn)
    webodm_options: dict[str, Any] = Field(default_factory=dict)
    start_immediately: bool = True

    @model_validator(mode="after")
    def _validate_input_source(self) -> MappingJobCreateIn:
        if self.processor.strip().lower() != "webodm":
            raise ValueError("Only processor='webodm' is currently supported.")
        if self.input_source == "drone_sync" and self.start_immediately is False:
            raise ValueError("input_source='drone_sync' requires start_immediately=true.")
        if self.input_source == "upload" and self.start_immediately is True:
            raise ValueError(
                "input_source='upload' requires start_immediately=false. "
                "Upload images first, then call /mapping/jobs/{job_id}/start."
            )
        return self


class MappingJobCreateOut(BaseModel):
    job_id: int
    field_id: int
    model_id: int
    status: str
    processor: str


class MappingAssetOut(BaseModel):
    id: int
    type: str
    url: str
    meta_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MappingJobStatusOut(BaseModel):
    job_id: int
    field_id: int
    model_id: int
    status: str
    progress: int
    created_at: datetime
    error: str | None = None
    processor: str
    processor_task_id: str | None = None
    assets: list[MappingAssetOut] = Field(default_factory=list)


class MappingJobUploadOut(BaseModel):
    job_id: int
    uploaded_count: int
    uploaded_paths: list[str]


class MappingJobDeleteOut(BaseModel):
    job_id: int
    deleted: bool = True


class FieldModelVersionOut(BaseModel):
    id: int
    version: int
    status: str
    created_at: datetime
    coordinate_system: str = "EPSG:4326"


class FieldRegistryOut(BaseModel):
    field_id: int
    field_name: str
    owner_id: int
    coordinate_system: str = "EPSG:4326"
    versions: list[FieldModelVersionOut]


class MappingSignedUrlOut(BaseModel):
    asset_id: int
    asset_type: str
    expires_at: datetime
    relative_url: str
    url: str
    path: str | None = None


async def _get_owned_field_or_404(
    db: AsyncSession,
    *,
    field_id: int,
    user,
) -> FieldEntity:
    field = await mapping_application.get_field(db, field_id=field_id, user=user)
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


async def _get_owned_job_or_404(
    db: AsyncSession,
    *,
    job_id: int,
    user,
) -> MappingJob:
    job = await mapping_application.get_job(db, job_id=job_id, user=user)
    if not job:
        raise HTTPException(status_code=404, detail="Mapping job not found")
    return job


async def _get_owned_asset_or_404(
    db: AsyncSession,
    *,
    asset_id: int,
    user,
) -> tuple[Asset, int]:
    pair = await mapping_application.get_asset(db, asset_id=asset_id, user=user)
    if not pair:
        raise HTTPException(status_code=404, detail="Asset not found")
    return pair


async def _assets_for_model(db: AsyncSession, *, model_id: int) -> list[Asset]:
    return await mapping_application.assets_for_model(db, model_id=model_id)


async def _latest_photogrammetry_source_dir(db: AsyncSession) -> str | None:
    return await mapping_application.latest_source_dir(db)


def _mapping_inputs_root() -> Path:
    return Path(settings.PHOTOGRAMMETRY_INPUTS_DIR).resolve()


def _mapping_allowed_extensions() -> set[str]:
    allowed_exts = {
        ext.strip().lower()
        for ext in settings.photogrammetry_allowed_image_extensions.split(",")
        if ext.strip()
    }
    return allowed_exts or {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


def _mapping_max_upload_files() -> int:
    return settings.photogrammetry_max_upload_files


def _mapping_max_upload_file_bytes() -> int:
    return settings.photogrammetry_max_upload_file_bytes


def _parse_form_object(raw: str | None, *, field_name: str) -> dict[str, Any]:
    if raw is None or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON object")
    return value


async def _persist_upload_files(
    files: list[UploadFile],
    *,
    destination_dir: Path,
) -> list[Path]:
    max_upload_files = _mapping_max_upload_files()
    if len(files) > max_upload_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files uploaded ({len(files)} > {max_upload_files}).",
        )

    max_upload_file_bytes = _mapping_max_upload_file_bytes()
    allowed_exts = _mapping_allowed_extensions()
    destination_dir.mkdir(parents=True, exist_ok=True)

    stored_paths: list[Path] = []
    for upload in files:
        safe_name = Path(upload.filename or "upload.bin").name
        if not safe_name:
            await upload.close()
            continue

        ext = Path(safe_name).suffix.lower()
        if ext not in allowed_exts:
            await upload.close()
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}' for '{safe_name}'.",
            )

        dst = destination_dir / (f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}_{safe_name}")
        size = 0
        try:
            with dst.open("wb") as out:
                while True:
                    chunk = await upload.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_upload_file_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                f"Uploaded file '{safe_name}' exceeds "
                                f"PHOTOGRAMMETRY_MAX_UPLOAD_FILE_BYTES={max_upload_file_bytes}."
                            ),
                        )
                    out.write(chunk)
        except Exception:
            if dst.exists():
                dst.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        if size == 0:
            dst.unlink(missing_ok=True)
            continue
        stored_paths.append(dst)

    return stored_paths


def _relative_input_paths(paths: list[Path], *, inputs_root: Path) -> list[str]:
    return [str(path.relative_to(inputs_root)) for path in paths]


def _move_staged_uploads_into_job(
    staged_paths: list[Path],
    *,
    inputs_root: Path,
    job_id: int,
) -> list[Path]:
    job_dir = inputs_root / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    moved_paths: list[Path] = []
    for src in staged_paths:
        dst = job_dir / src.name
        if dst.exists():
            dst = job_dir / f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}_{src.name}"
        shutil.move(str(src), str(dst))
        moved_paths.append(dst)
    return moved_paths


async def _create_field_from_ring(
    db: AsyncSession,
    *,
    user,
    name: str,
    ring: list[list[float]],
) -> FieldEntity:
    field = await mapping_application.create_derived_field(db, user=user, name=name, ring=ring)
    if field is None:
        raise HTTPException(status_code=500, detail="Failed to create field for uploaded images")
    return field


def _auto_generated_field_name() -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"Uploaded field {stamp}"


def _to_job_status(job: MappingJob, assets: list[Asset]) -> MappingJobStatusOut:
    return MappingJobStatusOut(
        job_id=job.id,
        field_id=job.field_id,
        model_id=job.model_id,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        error=job.error,
        processor=job.processor,
        processor_task_id=job.processor_task_id,
        assets=[
            MappingAssetOut(
                id=a.id,
                type=a.type,
                url=a.url,
                meta_data=a.meta_data or {},
                created_at=a.created_at,
            )
            for a in assets
        ],
    )


async def _enqueue_job_or_503(db: AsyncSession, *, job: MappingJob) -> None:
    try:
        task_id = _job_queue().enqueue(job_id=job.id)
    except MappingJobQueueError as exc:
        msg = "Failed to enqueue mapping job. Ensure Redis broker and Celery workers are running."
        logger.error("Failed to enqueue mapping job %s: %s", job.id, str(exc))
        await mapping_application.mark_enqueue_failed(db, job=job, error=msg)
        raise HTTPException(status_code=503, detail=msg) from exc

    await mapping_application.mark_enqueued(db, job=job, task_id=task_id)


@router.post("/jobs", response_model=MappingJobCreateOut)
async def create_mapping_job(
    payload: MappingJobCreateIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> MappingJobCreateOut:
    user = org_user.user
    field = await _get_owned_field_or_404(db, field_id=payload.field_id, user=user)
    params = payload.model_dump()
    if params.get("input_source") == "drone_sync":
        drone_sync = params.get("drone_sync")
        if not isinstance(drone_sync, dict):
            drone_sync = {}
        source_dir = drone_sync.get("source_dir")
        if not isinstance(source_dir, str) or not source_dir.strip():
            inferred = await _latest_photogrammetry_source_dir(db)
            if inferred:
                drone_sync["source_dir"] = inferred
                params["drone_sync"] = drone_sync
                logger.info("Auto-filled mapping source_dir from latest flight: %s", inferred)

    model_id, job = await mapping_application.create_job(
        db, field=field, processor=payload.processor, params=params
    )

    if payload.start_immediately:
        await _enqueue_job_or_503(db, job=job)
        await mapping_application.refresh(db, job=job)

    return MappingJobCreateOut(
        job_id=job.id,
        field_id=field.id,
        model_id=model_id,
        status=job.status,
        processor=job.processor,
    )


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

    inputs_root = _mapping_inputs_root()
    staging_root = inputs_root / "_staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix="mapping-upload-", dir=str(staging_root)))

    try:
        staged_paths = await _persist_upload_files(files, destination_dir=stage_dir)
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

        resolved_field_name = (field_name or "").strip() or _auto_generated_field_name()
        artifacts_payload = MappingArtifactsIn.model_validate(
            _parse_form_object(artifacts, field_name="artifacts")
        )
        webodm_options_payload = _parse_form_object(
            webodm_options,
            field_name="webodm_options",
        )

        field = await _create_field_from_ring(
            db,
            user=user,
            name=resolved_field_name,
            ring=derived_ring,
        )
        _model_id, job = await mapping_application.create_uncommitted_job(
            db, field=field, processor=processor.strip().lower(), status="uploading"
        )

        stored_paths = _move_staged_uploads_into_job(
            staged_paths,
            inputs_root=inputs_root,
            job_id=job.id,
        )
        relative_paths = _relative_input_paths(stored_paths, inputs_root=inputs_root)
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

        await _enqueue_job_or_503(db, job=job)
        await mapping_application.refresh(db, job=job)
        return _to_job_status(job, [])
    except Exception:
        await mapping_application.rollback(db)
        raise
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


@router.get("/jobs", response_model=list[MappingJobStatusOut])
async def list_mapping_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[MappingJobStatusOut]:
    user = org_user.user
    rows = await mapping_application.list_jobs_with_assets(db, user=user, limit=limit)
    return [_to_job_status(job, assets) for job, assets in rows]


@router.get("/jobs/{job_id}", response_model=MappingJobStatusOut)
async def get_mapping_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> MappingJobStatusOut:
    job = await _get_owned_job_or_404(db, job_id=job_id, user=org_user.user)
    assets = await _assets_for_model(db, model_id=job.model_id)
    return _to_job_status(job, assets)


@router.get("/fields/{field_id}/latest-ready", response_model=MappingJobStatusOut)
async def get_latest_ready_mapping_for_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> MappingJobStatusOut:
    field = await _get_owned_field_or_404(db, field_id=field_id, user=org_user.user)

    latest = await mapping_application.latest_ready(db, field_id=field.id)
    if not latest:
        raise HTTPException(status_code=404, detail="No ready mapping model for this field")
    job, assets = latest
    return _to_job_status(job, assets)


@router.get("/fields/{field_id}/models", response_model=list[FieldModelVersionOut])
async def list_field_model_versions(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[FieldModelVersionOut]:
    field = await _get_owned_field_or_404(db, field_id=field_id, user=org_user.user)
    versions = await mapping_application.list_versions(db, field_id=field.id)
    return [
        FieldModelVersionOut(
            id=v.id,
            version=v.version,
            status=v.status,
            created_at=v.created_at,
        )
        for v in versions
    ]


@router.get("/fields/{field_id}/registry", response_model=FieldRegistryOut)
async def get_field_registry(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> FieldRegistryOut:
    user = org_user.user
    field = await _get_owned_field_or_404(db, field_id=field_id, user=user)
    versions = await mapping_application.list_versions(db, field_id=field.id)
    return FieldRegistryOut(
        field_id=field.id,
        field_name=field.name,
        owner_id=int(field.owner_id or user.id),
        coordinate_system="EPSG:4326",
        versions=[
            FieldModelVersionOut(
                id=v.id,
                version=v.version,
                status=v.status,
                created_at=v.created_at,
            )
            for v in versions
        ],
    )


@router.post("/jobs/{job_id}/start", response_model=MappingJobStatusOut)
async def start_mapping_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> MappingJobStatusOut:
    job = await _get_owned_job_or_404(db, job_id=job_id, user=org_user.user)
    if job.status in {"processing", "ready"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start job in status '{job.status}'",
        )

    await _enqueue_job_or_503(db, job=job)
    await mapping_application.refresh(db, job=job)

    assets = await _assets_for_model(db, model_id=job.model_id)
    return _to_job_status(job, assets)


@router.post("/jobs/{job_id}/images", response_model=MappingJobUploadOut)
async def upload_mapping_job_images(
    job_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> MappingJobUploadOut:
    job = await _get_owned_job_or_404(db, job_id=job_id, user=org_user.user)
    if job.status not in {"pending", "uploading", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot upload inputs while job is '{job.status}'",
        )

    inputs_root = _mapping_inputs_root()
    job_dir = inputs_root / str(job.id)
    stored_paths = await _persist_upload_files(files, destination_dir=job_dir)
    uploaded_paths = _relative_input_paths(stored_paths, inputs_root=inputs_root)

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
    job = await _get_owned_job_or_404(db, job_id=job_id, user=org_user.user)
    if job.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a mapping job while processing is active.",
        )

    await mapping_application.delete_job(db, job=job)
    shutil.rmtree(_mapping_inputs_root() / str(job_id), ignore_errors=True)
    return MappingJobDeleteOut(job_id=job_id, deleted=True)


@router.get("/assets/{asset_id}/signed-url", response_model=MappingSignedUrlOut)
async def get_mapping_asset_signed_url(
    asset_id: int,
    request: Request,
    ttl_seconds: int = Query(default=900, ge=60, le=86400),
    path: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> MappingSignedUrlOut:
    clean_path = path.strip().lstrip("/")
    if ".." in Path(clean_path).parts:
        raise HTTPException(status_code=400, detail="Invalid asset sub-path")

    asset, owner_id = await _get_owned_asset_or_404(db, asset_id=asset_id, user=org_user.user)
    gateway = _asset_gateway()
    relative_url, exp = gateway.build_signed_url(
        asset_id=asset.id,
        user_id=owner_id,
        ttl_seconds=ttl_seconds,
        path=clean_path,
    )
    absolute_url = (
        await gateway.build_download_url(
            asset_id=asset.id,
            user_id=owner_id,
            org_id=org_user.org_id,
            asset_url=asset.url,
            asset_type=asset.type,
            ttl_seconds=ttl_seconds,
            path=clean_path,
        )
        if settings.storage_backend == "s3"
        else f"{str(request.base_url).rstrip('/')}{relative_url}"
    )
    return MappingSignedUrlOut(
        asset_id=asset.id,
        asset_type=asset.type,
        expires_at=datetime.fromtimestamp(exp, tz=UTC),
        relative_url=relative_url if settings.storage_backend != "s3" else "",
        url=absolute_url,
        path=clean_path or None,
    )


@router.get("/assets/{asset_id}/download")
async def download_mapping_asset(
    asset_id: int,
    exp: int = Query(...),
    sig: str = Query(...),
    path: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    clean_path = path.strip().lstrip("/")
    if ".." in Path(clean_path).parts:
        raise HTTPException(status_code=400, detail="Invalid asset sub-path")

    pair = await mapping_application.get_asset_record(db, asset_id=asset_id)
    if not pair:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset, owner_id, org_id = pair
    owner_id = int(owner_id)
    gateway = _asset_gateway()
    if not gateway.verify(
        asset_id=asset_id,
        user_id=owner_id,
        exp=exp,
        sig=sig,
        path=clean_path,
    ):
        raise HTTPException(status_code=403, detail="Invalid or expired asset token")

    local_target = gateway.resolve_local_target(
        asset_url=asset.url,
        asset_type=asset.type,
        path=clean_path,
    )
    headers = {"Cache-Control": "private, max-age=300"}
    if local_target:
        return FileResponse(str(local_target), headers=headers)

    if asset.url.startswith("http://") or asset.url.startswith("https://"):
        remote = asset.url.rstrip("/")
        if clean_path:
            remote = f"{remote}/{clean_path}"
        return RedirectResponse(remote, status_code=307, headers=headers)

    if settings.storage_backend == "s3":
        remote = await gateway.build_download_url(
            asset_id=asset.id,
            user_id=owner_id,
            org_id=int(org_id) if org_id is not None else None,
            asset_url=asset.url,
            asset_type=asset.type,
            ttl_seconds=max(60, exp - int(datetime.now(UTC).timestamp())),
            path=clean_path,
        )
        return RedirectResponse(remote, status_code=307, headers=headers)

    raise HTTPException(status_code=404, detail="Asset content not available")
