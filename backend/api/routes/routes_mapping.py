from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import require_user
from backend.db.models import Asset, Field as FieldEntity, FieldModel, MappingJob
from backend.db.session import get_db
from backend.services.photogrammetry.asset_gateway import AssetGatewayService
from backend.services.photogrammetry.field_registry import FieldRegistryService
from backend.services.photogrammetry.queue import MappingJobQueue, MappingJobQueueError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mapping", tags=["mapping"])
field_registry = FieldRegistryService()
asset_gateway = AssetGatewayService()
job_queue = MappingJobQueue()


class MappingArtifactsIn(BaseModel):
    orthomosaic: bool = True
    dsm: bool = True
    dtm: bool = False
    textured_mesh: bool = True
    point_cloud: bool = False
    xyz_tiles: bool = True


class MappingDroneSyncIn(BaseModel):
    source_dir: Optional[str] = None
    recursive: bool = True


class MappingJobCreateIn(BaseModel):
    field_id: int
    processor: str = "webodm"
    input_source: Literal["upload", "drone_sync"] = "upload"
    drone_sync: Optional[MappingDroneSyncIn] = None
    artifacts: MappingArtifactsIn = Field(default_factory=MappingArtifactsIn)
    webodm_options: Dict[str, Any] = Field(default_factory=dict)
    start_immediately: bool = True

    @model_validator(mode="after")
    def _validate_input_source(self) -> "MappingJobCreateIn":
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
    meta_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MappingJobStatusOut(BaseModel):
    job_id: int
    field_id: int
    model_id: int
    status: str
    progress: int
    error: Optional[str] = None
    processor: str
    processor_task_id: Optional[str] = None
    assets: List[MappingAssetOut] = Field(default_factory=list)


class MappingJobUploadOut(BaseModel):
    job_id: int
    uploaded_count: int
    uploaded_paths: List[str]


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
    versions: List[FieldModelVersionOut]


class MappingSignedUrlOut(BaseModel):
    asset_id: int
    asset_type: str
    expires_at: datetime
    relative_url: str
    url: str
    path: Optional[str] = None


async def _get_owned_field_or_404(
    db: AsyncSession,
    *,
    field_id: int,
    owner_id: int,
) -> FieldEntity:
    field = await field_registry.get_owned_field(db, field_id=field_id, owner_id=owner_id)
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


async def _get_owned_job_or_404(
    db: AsyncSession,
    *,
    job_id: int,
    owner_id: int,
) -> MappingJob:
    row = await db.execute(
        select(MappingJob, FieldEntity)
        .join(FieldEntity, MappingJob.field_id == FieldEntity.id)
        .where(MappingJob.id == job_id, FieldEntity.owner_id == owner_id)
    )
    pair = row.first()
    if not pair:
        raise HTTPException(status_code=404, detail="Mapping job not found")
    job, _field = pair
    return job


async def _get_owned_asset_or_404(
    db: AsyncSession,
    *,
    asset_id: int,
    owner_id: int,
) -> tuple[Asset, int]:
    row = await db.execute(
        select(Asset, FieldEntity.owner_id)
        .join(FieldModel, Asset.model_id == FieldModel.id)
        .join(FieldEntity, FieldModel.field_id == FieldEntity.id)
        .where(Asset.id == asset_id)
    )
    pair = row.first()
    if not pair:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset, field_owner_id = pair
    if int(field_owner_id) != int(owner_id):
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset, int(field_owner_id)


async def _assets_for_model(db: AsyncSession, *, model_id: int) -> List[Asset]:
    return (
        await db.execute(select(Asset).where(Asset.model_id == model_id).order_by(Asset.id.asc()))
    ).scalars().all()


def _to_job_status(job: MappingJob, assets: List[Asset]) -> MappingJobStatusOut:
    return MappingJobStatusOut(
        job_id=job.id,
        field_id=job.field_id,
        model_id=job.model_id,
        status=job.status,
        progress=job.progress,
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
        task_id = job_queue.enqueue(job_id=job.id)
    except MappingJobQueueError as exc:
        msg = str(exc)
        logger.error("Failed to enqueue mapping job %s: %s", job.id, msg)
        job.status = "failed"
        job.error = msg
        await db.commit()
        raise HTTPException(status_code=503, detail=msg)

    job.status = "pending"
    job.progress = 0
    job.error = None
    job.processor_task_id = task_id
    await db.commit()


@router.post("/jobs", response_model=MappingJobCreateOut)
async def create_mapping_job(
    payload: MappingJobCreateIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> MappingJobCreateOut:
    field = await _get_owned_field_or_404(db, field_id=payload.field_id, owner_id=user.id)
    version = await field_registry.next_model_version(db, field_id=field.id)

    model = FieldModel(
        field_id=field.id,
        version=version,
        status="pending",
    )
    db.add(model)
    await db.flush()

    job = MappingJob(
        field_id=field.id,
        model_id=model.id,
        status="pending",
        progress=0,
        processor=payload.processor,
        params=payload.model_dump(),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    if payload.start_immediately:
        await _enqueue_job_or_503(db, job=job)
        await db.refresh(job)

    return MappingJobCreateOut(
        job_id=job.id,
        field_id=field.id,
        model_id=model.id,
        status=job.status,
        processor=job.processor,
    )


@router.get("/jobs/{job_id}", response_model=MappingJobStatusOut)
async def get_mapping_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> MappingJobStatusOut:
    job = await _get_owned_job_or_404(db, job_id=job_id, owner_id=user.id)
    assets = await _assets_for_model(db, model_id=job.model_id)
    return _to_job_status(job, assets)


@router.get("/fields/{field_id}/latest-ready", response_model=MappingJobStatusOut)
async def get_latest_ready_mapping_for_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> MappingJobStatusOut:
    field = await _get_owned_field_or_404(db, field_id=field_id, owner_id=user.id)

    model = (
        await db.execute(
            select(FieldModel)
            .where(FieldModel.field_id == field.id, FieldModel.status == "ready")
            .order_by(FieldModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="No ready mapping model for this field")

    job = (
        await db.execute(
            select(MappingJob)
            .where(MappingJob.model_id == model.id)
            .order_by(MappingJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="No mapping job found for latest model")

    assets = await _assets_for_model(db, model_id=model.id)
    return _to_job_status(job, assets)


@router.get("/fields/{field_id}/models", response_model=List[FieldModelVersionOut])
async def list_field_model_versions(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> List[FieldModelVersionOut]:
    field = await _get_owned_field_or_404(db, field_id=field_id, owner_id=user.id)
    versions = await field_registry.list_versions(db, field_id=field.id)
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
    user=Depends(require_user),
) -> FieldRegistryOut:
    field = await _get_owned_field_or_404(db, field_id=field_id, owner_id=user.id)
    versions = await field_registry.list_versions(db, field_id=field.id)
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
    user=Depends(require_user),
) -> MappingJobStatusOut:
    job = await _get_owned_job_or_404(db, job_id=job_id, owner_id=user.id)
    if job.status in {"processing", "ready"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start job in status '{job.status}'",
        )

    await _enqueue_job_or_503(db, job=job)
    await db.refresh(job)

    assets = await _assets_for_model(db, model_id=job.model_id)
    return _to_job_status(job, assets)


@router.post("/jobs/{job_id}/images", response_model=MappingJobUploadOut)
async def upload_mapping_job_images(
    job_id: int,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> MappingJobUploadOut:
    job = await _get_owned_job_or_404(db, job_id=job_id, owner_id=user.id)
    if job.status not in {"pending", "uploading", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot upload inputs while job is '{job.status}'",
        )

    max_upload_files = int(os.getenv("PHOTOGRAMMETRY_MAX_UPLOAD_FILES", "5000"))
    if len(files) > max_upload_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files uploaded ({len(files)} > {max_upload_files}).",
        )

    max_upload_file_bytes = int(os.getenv("PHOTOGRAMMETRY_MAX_UPLOAD_FILE_BYTES", str(1024 * 1024 * 1024)))
    allowed_exts = {
        ext.strip().lower()
        for ext in os.getenv(
            "PHOTOGRAMMETRY_ALLOWED_IMAGE_EXTENSIONS",
            ".jpg,.jpeg,.png,.tif,.tiff,.webp",
        ).split(",")
        if ext.strip()
    }
    if not allowed_exts:
        allowed_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

    inputs_root = Path(
        os.getenv("PHOTOGRAMMETRY_INPUTS_DIR", "backend/storage/mapping_jobs_inputs")
    ).resolve()
    job_dir = inputs_root / str(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)

    uploaded_paths: List[str] = []
    for f in files:
        safe_name = Path(f.filename or "upload.bin").name
        if not safe_name:
            continue
        ext = Path(safe_name).suffix.lower()
        if ext not in allowed_exts:
            await f.close()
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}' for '{safe_name}'.",
            )

        dst = job_dir / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
        size = 0
        try:
            with dst.open("wb") as out:
                while True:
                    chunk = await f.read(8 * 1024 * 1024)
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
            await f.close()

        if size == 0:
            dst.unlink(missing_ok=True)
            continue
        uploaded_paths.append(str(dst.relative_to(inputs_root)))

    params = job.params if isinstance(job.params, dict) else {}
    existing = params.get("uploaded_images")
    if not isinstance(existing, list):
        existing = []
    existing.extend(uploaded_paths)
    params["uploaded_images"] = existing
    params["uploaded_count"] = len(existing)
    job.params = params
    job.status = "uploading" if existing else job.status
    await db.commit()

    return MappingJobUploadOut(
        job_id=job.id,
        uploaded_count=len(uploaded_paths),
        uploaded_paths=uploaded_paths,
    )


@router.get("/assets/{asset_id}/signed-url", response_model=MappingSignedUrlOut)
async def get_mapping_asset_signed_url(
    asset_id: int,
    request: Request,
    ttl_seconds: int = Query(default=900, ge=60, le=86400),
    path: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> MappingSignedUrlOut:
    clean_path = path.strip().lstrip("/")
    if ".." in Path(clean_path).parts:
        raise HTTPException(status_code=400, detail="Invalid asset sub-path")

    asset, owner_id = await _get_owned_asset_or_404(db, asset_id=asset_id, owner_id=user.id)
    relative_url, exp = asset_gateway.build_signed_url(
        asset_id=asset.id,
        user_id=owner_id,
        ttl_seconds=ttl_seconds,
        path=clean_path,
    )
    absolute_url = f"{str(request.base_url).rstrip('/')}{relative_url}"
    return MappingSignedUrlOut(
        asset_id=asset.id,
        asset_type=asset.type,
        expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
        relative_url=relative_url,
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

    row = await db.execute(
        select(Asset, FieldEntity.owner_id)
        .join(FieldModel, Asset.model_id == FieldModel.id)
        .join(FieldEntity, FieldModel.field_id == FieldEntity.id)
        .where(Asset.id == asset_id)
    )
    pair = row.first()
    if not pair:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset, owner_id = pair
    owner_id = int(owner_id)
    if not asset_gateway.verify(
        asset_id=asset_id,
        user_id=owner_id,
        exp=exp,
        sig=sig,
        path=clean_path,
    ):
        raise HTTPException(status_code=403, detail="Invalid or expired asset token")

    local_target = asset_gateway.resolve_local_target(
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

    raise HTTPException(status_code=404, detail="Asset content not available")
