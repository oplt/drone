from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.modules.fields.models import Field as FieldEntity
from backend.modules.mapping.api.mapping_route_schemas import (
    MappingAssetOut,
    MappingJobStatusOut,
)
from backend.modules.mapping.application import mapping_application
from backend.modules.mapping.models import Asset, MappingJob
from backend.modules.mapping.service.asset_gateway import AssetGatewayService
from backend.modules.mapping.service.queue import MappingJobQueue, MappingJobQueueError

logger = logging.getLogger(__name__)


def asset_gateway() -> AssetGatewayService:
    return AssetGatewayService()


def job_queue() -> MappingJobQueue:
    return MappingJobQueue()


async def get_owned_field_or_404(
    db: AsyncSession,
    *,
    field_id: int,
    user,
) -> FieldEntity:
    field = await mapping_application.get_field(db, field_id=field_id, user=user)
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


async def get_owned_job_or_404(
    db: AsyncSession,
    *,
    job_id: int,
    user,
) -> MappingJob:
    job = await mapping_application.get_job(db, job_id=job_id, user=user)
    if not job:
        raise HTTPException(status_code=404, detail="Mapping job not found")
    return job


async def get_owned_asset_or_404(
    db: AsyncSession,
    *,
    asset_id: int,
    user,
) -> tuple[Asset, int]:
    pair = await mapping_application.get_asset(db, asset_id=asset_id, user=user)
    if not pair:
        raise HTTPException(status_code=404, detail="Asset not found")
    return pair


async def assets_for_model(db: AsyncSession, *, model_id: int) -> list[Asset]:
    return await mapping_application.assets_for_model(db, model_id=model_id)


async def latest_photogrammetry_source_dir(db: AsyncSession) -> str | None:
    return await mapping_application.latest_source_dir(db)


def mapping_inputs_root() -> Path:
    return Path(settings.PHOTOGRAMMETRY_INPUTS_DIR).resolve()


def mapping_allowed_extensions() -> set[str]:
    allowed_exts = {
        ext.strip().lower()
        for ext in settings.photogrammetry_allowed_image_extensions.split(",")
        if ext.strip()
    }
    return allowed_exts or {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


def mapping_max_upload_files() -> int:
    return settings.photogrammetry_max_upload_files


def mapping_max_upload_file_bytes() -> int:
    return settings.photogrammetry_max_upload_file_bytes


def parse_form_object(raw: str | None, *, field_name: str) -> dict[str, Any]:
    if raw is None or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON object")
    return value


async def persist_upload_files(
    files: list[UploadFile],
    *,
    destination_dir: Path,
) -> list[Path]:
    max_upload_files = mapping_max_upload_files()
    if len(files) > max_upload_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files uploaded ({len(files)} > {max_upload_files}).",
        )

    max_upload_file_bytes = mapping_max_upload_file_bytes()
    allowed_exts = mapping_allowed_extensions()
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


def relative_input_paths(paths: list[Path], *, inputs_root: Path) -> list[str]:
    return [str(path.relative_to(inputs_root)) for path in paths]


def move_staged_uploads_into_job(
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


async def create_field_from_ring(
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


def auto_generated_field_name() -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"Uploaded field {stamp}"


def to_job_status(job: MappingJob, assets: list[Asset]) -> MappingJobStatusOut:
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
                id=asset.id,
                type=asset.type,
                url=asset.url,
                meta_data=asset.meta_data or {},
                created_at=asset.created_at,
            )
            for asset in assets
        ],
    )


async def enqueue_job_or_503(db: AsyncSession, *, job: MappingJob) -> None:
    try:
        task_id = job_queue().enqueue(job_id=job.id)
    except MappingJobQueueError as exc:
        msg = "Failed to enqueue mapping job. Ensure Redis broker and Celery workers are running."
        logger.error("Failed to enqueue mapping job %s: %s", job.id, str(exc))
        await mapping_application.mark_enqueue_failed(db, job=job, error=msg)
        raise HTTPException(status_code=503, detail=msg) from exc

    await mapping_application.mark_enqueued(db, job=job, task_id=task_id)


def create_upload_staging_dir(inputs_root: Path) -> Path:
    staging_root = inputs_root / "_staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="mapping-upload-", dir=str(staging_root)))
