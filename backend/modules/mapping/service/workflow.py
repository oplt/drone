from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.infrastructure.photogrammetry.mesh_conversion import convert_outputs
from backend.modules.integrations.webhooks.service import WebhookDispatchService
from backend.modules.mapping.models import Asset, FieldModel, MappingJob
from backend.modules.mapping.ports import (
    MappingImageIngestPort,
    MappingProcessorPort,
    MappingStoragePort,
)
from backend.modules.mapping.service.field_derivation import (
    derive_field_ring_from_bbox_wgs84,
    ring_to_polygon_wkt,
)

logger = logging.getLogger(__name__)


class PhotogrammetryService:
    """
    Full mapping pipeline:
    1) request WebODM processing
    2) fetch outputs
    3) convert to streaming-friendly map formats
    4) upload + register assets
    """

    def __init__(
        self,
        processor: MappingProcessorPort,
        storage: MappingStoragePort,
        ingest: MappingImageIngestPort,
        notifications: WebhookDispatchService | None = None,
    ) -> None:
        self.webodm = processor
        self.storage = storage
        self.ingest = ingest
        self.notifications = notifications or WebhookDispatchService()

    async def process_job(
        self,
        *,
        job_id: int,
        progress_cb: Callable[[dict], None] | None = None,
    ) -> dict:
        try:
            async with Session() as db:
                job = await db.get(MappingJob, job_id)
                if not job:
                    raise ValueError(f"MappingJob {job_id} not found")
                if job.status == "ready":
                    return {"status": "ready", "assets": {}}

                model = await db.get(FieldModel, job.model_id)
                if not model:
                    raise ValueError(f"FieldModel {job.model_id} not found for MappingJob {job_id}")
                logger.info(
                    "Photogrammetry job started: job_id=%s field_id=%s model_id=%s status=%s",
                    job_id,
                    job.field_id,
                    model.id,
                    job.status,
                )

                params = job.params if isinstance(job.params, dict) else {}
                requested_artifacts = (
                    params.get("artifacts") if isinstance(params.get("artifacts"), dict) else {}
                )
                webodm_options = (
                    params.get("webodm_options")
                    if isinstance(params.get("webodm_options"), dict)
                    else {}
                )
                uploaded_images = (
                    params.get("uploaded_images")
                    if isinstance(params.get("uploaded_images"), list)
                    else []
                )
                input_source = str(params.get("input_source") or "upload").strip().lower()
                existing_task_id = job.processor_task_id

                if not uploaded_images:
                    if input_source == "drone_sync":
                        logger.info("Photogrammetry job %s ingesting drone-sync images", job_id)
                        uploaded_images = self.ingest.collect_images_for_job(
                            job_id=job_id,
                            field_id=job.field_id,
                            params=params,
                        )
                        params["uploaded_images"] = uploaded_images
                        params["uploaded_count"] = len(uploaded_images)
                        job.params = params
                        job.status = "uploading"
                        await db.commit()
                        logger.info(
                            "Photogrammetry job %s ingested %s images from drone-sync",
                            job_id,
                            len(uploaded_images),
                        )
                    else:
                        raise RuntimeError(
                            "No input images found for mapping job. "
                            "Upload images or use input_source='drone_sync'."
                        )

                job.status = "processing"
                job.progress = 1
                job.started_at = datetime.now(UTC)
                model.status = "processing"
                await db.commit()
                logger.info(
                    "Photogrammetry job %s moved to processing with %s input images",
                    job_id,
                    len(uploaded_images),
                )

            if existing_task_id:
                task_id = existing_task_id
                logger.info("Photogrammetry job %s resuming WebODM task: %s", job_id, task_id)
            else:
                logger.info("Photogrammetry job %s submitting task to WebODM", job_id)
                task_id = await self.webodm.create_task(
                    job_id=job_id,
                    options=webodm_options,
                    image_paths=[str(p) for p in uploaded_images],
                )
                await self._update_job(job_id, processor_task_id=task_id, progress=5)
                logger.info(
                    "Photogrammetry job %s WebODM task created: task_id=%s", job_id, task_id
                )

            poll_s = settings.webodm_poll_interval_s
            max_poll_s = settings.webodm_poll_max_interval_s

            if poll_s <= 0:
                logger.warning("WEBODM_POLL_INTERVAL_S must be > 0; falling back to 5 seconds.")
                poll_s = 5.0
            if max_poll_s <= 0:
                logger.warning(
                    "WEBODM_POLL_MAX_INTERVAL_S must be > 0; falling back to 30 seconds."
                )
                max_poll_s = 30.0
            if max_poll_s < poll_s:
                max_poll_s = poll_s

            last_logged_progress_bucket = -1
            while True:
                status = await self.webodm.get_task_status(task_id)
                progress = int(status.get("progress", 0))
                if progress_cb:
                    progress_cb({"progress": progress})
                progress_bucket = progress // 10
                if progress_bucket > last_logged_progress_bucket:
                    logger.info(
                        "Photogrammetry job %s WebODM progress: state=%s progress=%s%%",
                        job_id,
                        status.get("state"),
                        progress,
                    )
                    last_logged_progress_bucket = progress_bucket

                if status["state"] == "COMPLETED":
                    await self._update_job(job_id, progress=55)
                    logger.info("Photogrammetry job %s WebODM task completed", job_id)
                    break
                if status["state"] == "FAILED":
                    error_msg = status.get("error") or "WebODM task failed"
                    await self._mark_failed(job_id, error_msg)
                    logger.error(
                        "Photogrammetry job %s WebODM task failed: %s",
                        job_id,
                        error_msg,
                    )
                    raise RuntimeError(error_msg)
                await asyncio.sleep(poll_s)
                poll_s = min(poll_s * 1.5, max_poll_s)

            outputs = await self.webodm.download_outputs(task_id)
            await self._update_job(job_id, progress=65)
            logger.info(
                "Photogrammetry job %s outputs downloaded: keys=%s",
                job_id,
                sorted(outputs.keys()),
            )
            download_root = outputs.get("__download_root")
            if "__download_root" in outputs:
                outputs = {k: v for k, v in outputs.items() if k != "__download_root"}

            with tempfile.TemporaryDirectory(prefix=f"mapping-job-{job_id}-") as tmp_dir:
                work = Path(tmp_dir)
                converted, artifact_meta = await asyncio.to_thread(
                    convert_outputs,
                    outputs,
                    work,
                    requested_artifacts=requested_artifacts,
                )
                await self._update_job(job_id, progress=80)
                logger.info(
                    "Photogrammetry job %s conversion complete: artifacts=%s",
                    job_id,
                    sorted(converted.keys()),
                )

                uploaded = await self._upload_outputs(converted)
                await self._update_job(job_id, progress=90)
                logger.info(
                    "Photogrammetry job %s upload complete: uploaded=%s",
                    job_id,
                    sorted(uploaded.keys()),
                )

            await self._refresh_auto_created_field_boundary(
                job_id=job_id,
                artifact_meta=artifact_meta,
            )

            if download_root:
                try:
                    shutil.rmtree(download_root, ignore_errors=True)
                except Exception:
                    logger.warning("Failed to clean WebODM download directory: %s", download_root)

            await self._register_assets(
                job_id=job_id,
                model_id=model.id,
                uploaded=uploaded,
                artifact_meta=artifact_meta,
            )
            await self._mark_ready(job_id, model.id)
            logger.info(
                "Photogrammetry job %s completed successfully with %s assets",
                job_id,
                len(uploaded),
            )

            result = {
                "status": "ready",
                "assets": uploaded,
            }
            if progress_cb:
                progress_cb({"progress": 100})
            return result

        except Exception as exc:
            logger.exception("Photogrammetry processing failed for job %s", job_id)
            await self._mark_failed(job_id, str(exc))
            raise

    async def _upload_outputs(self, converted: dict[str, str]) -> dict[str, str]:
        logger.info("Uploading converted artifacts: count=%s", len(converted))

        async def _upload_one(key: str, path: str) -> tuple[str, str]:
            src = Path(path)
            if src.is_dir():
                url = await self.storage.upload_directory(str(src))
            else:
                url = await self.storage.upload_file(str(src))
            logger.info("Uploaded artifact: key=%s source=%s url=%s", key, src, url)
            return key, url

        tasks = [_upload_one(key, path) for key, path in converted.items()]
        if not tasks:
            return {}

        results = await asyncio.gather(*tasks)
        return dict(results)

    async def _register_assets(
        self,
        *,
        job_id: int,
        model_id: int,
        uploaded: dict[str, str],
        artifact_meta: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        type_map = {
            "orthomosaic_cog": "ORTHO_COG",
            "orthomosaic_xyz": "ORTHO_XYZ",
            "dsm_cog": "DSM_COG",
            "dtm_cog": "DTM_COG",
            "textured_mesh_3dtiles": "TILESET_3D",
            "point_cloud": "POINTCLOUD",
        }
        artifact_meta = artifact_meta or {}

        async with Session() as db:
            for key, url in uploaded.items():
                asset_type = type_map.get(key, key.upper())
                asset = await db.scalar(
                    select(Asset).where(Asset.model_id == model_id, Asset.type == asset_type)
                )
                metadata = {
                    "job_id": job_id,
                    "artifact_key": key,
                    **artifact_meta.get(key, {}),
                }
                if asset is None:
                    asset = Asset(
                        model_id=model_id,
                        type=asset_type,
                        url=url,
                        meta_data=metadata,
                    )
                    db.add(asset)
                else:
                    asset.url = url
                    asset.meta_data = metadata
            await db.commit()
        logger.info(
            "Registered %s assets for model_id=%s (job_id=%s)",
            len(uploaded),
            model_id,
            job_id,
        )

    async def _refresh_auto_created_field_boundary(
        self,
        *,
        job_id: int,
        artifact_meta: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        artifact_meta = artifact_meta or {}
        ring = None
        for key in ("textured_mesh_3dtiles", "orthomosaic_cog", "dsm_cog", "dtm_cog"):
            meta = artifact_meta.get(key)
            if not isinstance(meta, dict):
                continue
            bbox_wgs84 = meta.get("bbox_wgs84")
            if not isinstance(bbox_wgs84, dict):
                georef = meta.get("georef")
                if isinstance(georef, dict):
                    bbox_wgs84 = georef.get("bbox_wgs84")
            ring = derive_field_ring_from_bbox_wgs84(
                bbox_wgs84 if isinstance(bbox_wgs84, dict) else None
            )
            if ring:
                break

        if not ring:
            return

        async with Session() as db:
            job = await db.get(MappingJob, job_id)
            if not job:
                return

            params = job.params if isinstance(job.params, dict) else {}
            if not bool(params.get("auto_created_field")):
                return

            polygon_wkt = ring_to_polygon_wkt(ring)
            await db.execute(
                text(
                    """
                    UPDATE fields
                    SET
                        boundary = ST_GeomFromText(:polygon_wkt, 4326),
                        centroid = ST_Centroid(ST_GeomFromText(:polygon_wkt, 4326)),
                        area_ha = ST_Area(
                            ST_Transform(ST_GeomFromText(:polygon_wkt, 4326), 3857)
                        ) / 10000.0
                    WHERE id = :field_id
                    """
                ),
                {
                    "polygon_wkt": polygon_wkt,
                    "field_id": int(job.field_id),
                },
            )
            params["field_boundary_source"] = "mapping_outputs"
            job.params = params
            await db.commit()
        logger.info(
            "Refined auto-created field boundary from mapping outputs: job_id=%s field_id=%s",
            job_id,
            job.field_id if job else None,
        )

    async def _update_job(
        self,
        job_id: int,
        *,
        processor_task_id: str | None = None,
        progress: int | None = None,
    ) -> None:
        async with Session() as db:
            job = await db.get(MappingJob, job_id)
            if not job:
                return
            if processor_task_id is not None:
                job.processor_task_id = processor_task_id
            if progress is not None:
                job.progress = max(0, min(100, int(progress)))
            await db.commit()

    async def _mark_ready(self, job_id: int, model_id: int) -> None:
        async with Session() as db:
            job = await db.get(MappingJob, job_id)
            model = await db.get(FieldModel, model_id)
            if job:
                job.status = "ready"
                job.progress = 100
                job.finished_at = datetime.now(UTC)
            if model:
                model.status = "ready"
            if job:
                await self.notifications.enqueue(
                    db,
                    org_id=job.org_id,
                    event_type="mapping.ready",
                    payload={"id": job.id, "field_id": job.field_id, "model_id": model_id},
                    idempotency_key=f"mapping.ready:{job.id}",
                )
            await db.commit()
        logger.info("Marked mapping job ready: job_id=%s model_id=%s", job_id, model_id)

    async def _mark_failed(self, job_id: int, error: str | None) -> None:
        async with Session() as db:
            job = await db.get(MappingJob, job_id)
            if not job:
                return
            job.status = "failed"
            job.error = error
            job.finished_at = datetime.now(UTC)
            await db.commit()
        logger.error("Marked mapping job failed: job_id=%s error=%s", job_id, error)
