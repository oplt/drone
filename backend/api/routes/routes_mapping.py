from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import require_user
from backend.db.models import Asset, Field as FieldEntity, FieldModel, FlightEvent, MappingJob
from backend.db.session import get_db
from backend.services.photogrammetry.asset_gateway import AssetGatewayService
from backend.services.photogrammetry.field_derivation import (
    collect_image_gps_locations,
    derive_field_ring_from_points,
    ring_to_polygon_wkt,
)
from backend.services.photogrammetry.field_registry import FieldRegistryService
from backend.services.photogrammetry.queue import MappingJobQueue, MappingJobQueueError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mapping", tags=["mapping"])
field_registry = FieldRegistryService()


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


async def _latest_photogrammetry_source_dir(db: AsyncSession) -> str | None:
    row = await db.execute(
        select(FlightEvent.data)
        .where(FlightEvent.type == "photogrammetry_mapping_job_params")
        .order_by(FlightEvent.id.desc())
        .limit(1)
    )
    data = row.scalar_one_or_none()
    if not isinstance(data, dict):
        return None
    drone_sync = data.get("drone_sync")
    if not isinstance(drone_sync, dict):
        return None
    source_dir = drone_sync.get("source_dir")
    if not isinstance(source_dir, str) or not source_dir.strip():
        return None
    return source_dir.strip()


def _mapping_inputs_root() -> Path:
    return Path(
        os.getenv("PHOTOGRAMMETRY_INPUTS_DIR", "backend/storage/mapping_jobs_inputs")
    ).resolve()


def _mapping_allowed_extensions() -> set[str]:
    allowed_exts = {
        ext.strip().lower()
        for ext in os.getenv(
            "PHOTOGRAMMETRY_ALLOWED_IMAGE_EXTENSIONS",
            ".jpg,.jpeg,.png,.tif,.tiff,.webp",
        ).split(",")
        if ext.strip()
    }
    return allowed_exts or {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


def _mapping_max_upload_files() -> int:
    return int(os.getenv("PHOTOGRAMMETRY_MAX_UPLOAD_FILES", "5000"))


def _mapping_max_upload_file_bytes() -> int:
    return int(
        os.getenv("PHOTOGRAMMETRY_MAX_UPLOAD_FILE_BYTES", str(1024 * 1024 * 1024))
    )


def _parse_form_object(raw: str | None, *, field_name: str) -> Dict[str, Any]:
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
    files: List[UploadFile],
    *,
    destination_dir: Path,
) -> List[Path]:
    max_upload_files = _mapping_max_upload_files()
    if len(files) > max_upload_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files uploaded ({len(files)} > {max_upload_files}).",
        )

    max_upload_file_bytes = _mapping_max_upload_file_bytes()
    allowed_exts = _mapping_allowed_extensions()
    destination_dir.mkdir(parents=True, exist_ok=True)

    stored_paths: List[Path] = []
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

        dst = destination_dir / (
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
        )
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


def _relative_input_paths(paths: List[Path], *, inputs_root: Path) -> List[str]:
    return [str(path.relative_to(inputs_root)) for path in paths]


def _move_staged_uploads_into_job(
    staged_paths: List[Path],
    *,
    inputs_root: Path,
    job_id: int,
) -> List[Path]:
    job_dir = inputs_root / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    moved_paths: List[Path] = []
    for src in staged_paths:
        dst = job_dir / src.name
        if dst.exists():
            dst = job_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{src.name}"
        shutil.move(str(src), str(dst))
        moved_paths.append(dst)
    return moved_paths


async def _create_field_from_ring(
    db: AsyncSession,
    *,
    owner_id: int,
    name: str,
    ring: List[List[float]],
) -> FieldEntity:
    polygon_wkt = ring_to_polygon_wkt(ring)
    row = await db.execute(
        text(
            """
            INSERT INTO fields (owner_id, name, boundary, area_ha, centroid)
            VALUES (
                :owner_id,
                :name,
                ST_GeomFromText(:polygon_wkt, 4326),
                ST_Area(ST_Transform(ST_GeomFromText(:polygon_wkt, 4326), 3857)) / 10000.0,
                ST_Centroid(ST_GeomFromText(:polygon_wkt, 4326))
            )
            RETURNING id
            """
        ),
        {
            "owner_id": owner_id,
            "name": name,
            "polygon_wkt": polygon_wkt,
        },
    )
    field_id = int(row.scalar_one())
    field = await db.get(FieldEntity, field_id)
    if field is None:
        raise HTTPException(status_code=500, detail="Failed to create field for uploaded images")
    return field


def _auto_generated_field_name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"Uploaded field {stamp}"


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
        task_id = _job_queue().enqueue(job_id=job.id)
    except MappingJobQueueError as exc:
        msg = "Failed to enqueue mapping job. Ensure Redis broker and Celery workers are running."
        logger.error("Failed to enqueue mapping job %s: %s", job.id, str(exc))
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
                logger.info(
                    "Auto-filled mapping drone_sync.source_dir from latest photogrammetry session: %s",
                    inferred,
                )

    job = MappingJob(
        field_id=field.id,
        model_id=model.id,
        status="pending",
        progress=0,
        processor=payload.processor,
        params=params,
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


@router.post("/jobs/upload", response_model=MappingJobStatusOut)
async def create_mapping_job_from_uploaded_images(
    files: List[UploadFile] = File(...),
    field_name: Optional[str] = Form(default=None),
    processor: str = Form(default="webodm"),
    artifacts: str = Form(default=""),
    webodm_options: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> MappingJobStatusOut:
    if processor.strip().lower() != "webodm":
        raise HTTPException(status_code=400, detail="Only processor='webodm' is currently supported.")

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
            owner_id=user.id,
            name=resolved_field_name,
            ring=derived_ring,
        )
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
            status="uploading",
            progress=0,
            processor=processor.strip().lower(),
            params={},
        )
        db.add(job)
        await db.flush()

        stored_paths = _move_staged_uploads_into_job(
            staged_paths,
            inputs_root=inputs_root,
            job_id=job.id,
        )
        relative_paths = _relative_input_paths(stored_paths, inputs_root=inputs_root)
        job.params = {
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
        }
        await db.commit()
        await db.refresh(job)

        await _enqueue_job_or_503(db, job=job)
        await db.refresh(job)
        return _to_job_status(job, [])
    except Exception:
        await db.rollback()
        raise
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


@router.get("/jobs", response_model=List[MappingJobStatusOut])
async def list_mapping_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> List[MappingJobStatusOut]:
    jobs = (
        await db.execute(
            select(MappingJob)
            .join(FieldEntity, MappingJob.field_id == FieldEntity.id)
            .where(FieldEntity.owner_id == user.id)
            .order_by(MappingJob.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    if not jobs:
        return []

    model_ids = sorted({int(job.model_id) for job in jobs})
    assets = (
        await db.execute(
            select(Asset)
            .where(Asset.model_id.in_(model_ids))
            .order_by(Asset.model_id.asc(), Asset.id.asc())
        )
    ).scalars().all()

    assets_by_model: Dict[int, List[Asset]] = {}
    for asset in assets:
        assets_by_model.setdefault(int(asset.model_id), []).append(asset)

    return [_to_job_status(job, assets_by_model.get(int(job.model_id), [])) for job in jobs]


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

    inputs_root = _mapping_inputs_root()
    job_dir = inputs_root / str(job.id)
    stored_paths = await _persist_upload_files(files, destination_dir=job_dir)
    uploaded_paths = _relative_input_paths(stored_paths, inputs_root=inputs_root)

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


@router.delete("/jobs/{job_id}", response_model=MappingJobDeleteOut)
async def delete_mapping_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> MappingJobDeleteOut:
    job = await _get_owned_job_or_404(db, job_id=job_id, owner_id=user.id)
    if job.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a mapping job while processing is active.",
        )

    jobs_for_model = int(
        (
            await db.execute(
                select(func.count(MappingJob.id)).where(MappingJob.model_id == job.model_id)
            )
        ).scalar_one()
        or 0
    )
    if jobs_for_model <= 1:
        model = await db.get(FieldModel, job.model_id)
        if model is not None:
            await db.delete(model)
        else:
            await db.delete(job)
    else:
        await db.delete(job)

    await db.commit()
    shutil.rmtree(_mapping_inputs_root() / str(job_id), ignore_errors=True)
    return MappingJobDeleteOut(job_id=job_id, deleted=True)


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
    gateway = _asset_gateway()
    relative_url, exp = gateway.build_signed_url(
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

    raise HTTPException(status_code=404, detail="Asset content not available")
