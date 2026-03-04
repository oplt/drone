from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.db.models import Asset, FieldModel, MappingJob
from backend.db.session import Session
from backend.services.photogrammetry.ingest import DroneSyncIngestService
from backend.services.photogrammetry.storage import StorageService
from backend.services.photogrammetry.tiling import (
    convert_mesh_to_3dtiles,
    convert_to_cog,
    generate_xyz_tiles,
    inspect_raster_georeferencing,
)
from backend.services.photogrammetry.webodm_client import WebODMClient

logger = logging.getLogger(__name__)


class PhotogrammetryService:
    """
    Full mapping pipeline:
    1) request WebODM processing
    2) fetch outputs
    3) convert to streaming-friendly map formats
    4) upload + register assets
    """

    def __init__(self) -> None:
        self.webodm = WebODMClient()
        self.storage = StorageService()
        self.ingest = DroneSyncIngestService()

    async def process_job(
        self,
        *,
        job_id: int,
        progress_cb: Optional[Callable[[dict], None]] = None,
    ) -> dict:
        try:
            async with Session() as db:
                job = await db.get(MappingJob, job_id)
                if not job:
                    raise ValueError(f"MappingJob {job_id} not found")

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
                job.started_at = datetime.now(timezone.utc)
                model.status = "processing"
                await db.commit()
                logger.info(
                    "Photogrammetry job %s moved to processing with %s input images",
                    job_id,
                    len(uploaded_images),
                )

            logger.info("Photogrammetry job %s submitting task to WebODM", job_id)
            task_id = await self.webodm.create_task(
                job_id=job_id,
                options=webodm_options,
                image_paths=[str(p) for p in uploaded_images],
            )
            await self._update_job(job_id, processor_task_id=task_id, progress=5)
            logger.info("Photogrammetry job %s WebODM task created: task_id=%s", job_id, task_id)

            try:
                poll_s = float(os.getenv("WEBODM_POLL_INTERVAL_S", "5"))
            except ValueError:
                logger.warning(
                    "Invalid WEBODM_POLL_INTERVAL_S value; falling back to 5 seconds."
                )
                poll_s = 5.0

            try:
                max_poll_s = float(os.getenv("WEBODM_POLL_MAX_INTERVAL_S", "30"))
            except ValueError:
                logger.warning(
                    "Invalid WEBODM_POLL_MAX_INTERVAL_S value; falling back to 30 seconds."
                )
                max_poll_s = 30.0

            if poll_s <= 0:
                logger.warning(
                    "WEBODM_POLL_INTERVAL_S must be > 0; falling back to 5 seconds."
                )
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
                    self._convert_outputs,
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

    def _convert_outputs(
        self,
        outputs: Dict[str, str],
        work_dir: Path,
        *,
        requested_artifacts: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
        work_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Photogrammetry conversion started: work_dir=%s requested_artifacts=%s",
            work_dir,
            requested_artifacts or {},
        )

        converted: Dict[str, str] = {}
        artifact_meta: Dict[str, Dict[str, Any]] = {}

        requested_artifacts = requested_artifacts or {}

        def enabled(name: str, default: bool) -> bool:
            val = requested_artifacts.get(name)
            if val is None:
                return default
            return bool(val)

        ortho_enabled = enabled("orthomosaic", True)
        dsm_enabled = enabled("dsm", True)
        dtm_enabled = enabled("dtm", False)
        mesh_enabled = enabled("textured_mesh", True)
        xyz_enabled = enabled("xyz_tiles", True)
        point_cloud_enabled = enabled("point_cloud", False)

        ortho_cog: Optional[str] = None
        mesh_georef: Optional[dict[str, Any]] = None

        if ortho_enabled:
            ortho_src = outputs.get("orthophoto")
            if not ortho_src:
                raise RuntimeError("WebODM output missing required orthophoto")
            ortho_cog = convert_to_cog(ortho_src, str(work_dir / "orthomosaic.cog.tif"))
            ortho_georef = inspect_raster_georeferencing(ortho_cog)
            converted["orthomosaic_cog"] = ortho_cog
            artifact_meta["orthomosaic_cog"] = {
                "georef": ortho_georef,
                "source": "orthophoto",
            }
            if mesh_georef is None and isinstance(ortho_georef, dict):
                mesh_georef = ortho_georef
            logger.info("Converted orthomosaic COG: %s", ortho_cog)

        if dsm_enabled:
            dsm_src = outputs.get("dsm")
            if not dsm_src:
                raise RuntimeError("WebODM output missing required DSM")
            dsm_cog = convert_to_cog(dsm_src, str(work_dir / "dsm.cog.tif"))
            dsm_georef = inspect_raster_georeferencing(dsm_cog)
            converted["dsm_cog"] = dsm_cog
            artifact_meta["dsm_cog"] = {
                "georef": dsm_georef,
                "source": "dsm",
            }
            if mesh_georef is None and isinstance(dsm_georef, dict):
                mesh_georef = dsm_georef
            logger.info("Converted DSM COG: %s", dsm_cog)

        if dtm_enabled:
            dtm_src = outputs.get("dtm")
            if dtm_src:
                dtm_cog = convert_to_cog(dtm_src, str(work_dir / "dtm.cog.tif"))
                dtm_georef = inspect_raster_georeferencing(dtm_cog)
                converted["dtm_cog"] = dtm_cog
                artifact_meta["dtm_cog"] = {
                    "georef": dtm_georef,
                    "source": "dtm",
                }
                if mesh_georef is None and isinstance(dtm_georef, dict):
                    mesh_georef = dtm_georef
                logger.info("Converted DTM COG: %s", dtm_cog)
            else:
                logger.warning("DTM requested but not available in WebODM outputs")

        if xyz_enabled and ortho_cog:
            # Optional XYZ for mobile/offline map use.
            xyz_dir = generate_xyz_tiles(ortho_cog, str(work_dir / "orthomosaic_xyz"))
            if xyz_dir:
                converted["orthomosaic_xyz"] = xyz_dir
                artifact_meta["orthomosaic_xyz"] = {
                    "source": "orthomosaic_cog",
                    "format": "xyz",
                }
                logger.info("Generated XYZ tiles: %s", xyz_dir)

        if mesh_enabled:
            mesh_src = outputs.get("mesh")
            if not mesh_src:
                raise RuntimeError("WebODM output missing required mesh")
            tileset_dir = convert_mesh_to_3dtiles(
                mesh_src,
                str(work_dir / "mesh_3dtiles"),
                georef=mesh_georef,
            )
            converted["textured_mesh_3dtiles"] = tileset_dir
            artifact_meta["textured_mesh_3dtiles"] = {
                "source": "mesh",
                "format": "3dtiles",
                "georef": mesh_georef,
                "bbox_wgs84": (
                    mesh_georef.get("bbox_wgs84")
                    if isinstance(mesh_georef, dict)
                    else None
                ),
            }
            logger.info("Generated textured mesh 3D tiles: %s", tileset_dir)

        if point_cloud_enabled:
            point_cloud_src = outputs.get("point_cloud")
            if point_cloud_src:
                src = Path(point_cloud_src).resolve()
                dst = work_dir / src.name
                if src != dst:
                    shutil.copy2(src, dst)
                converted["point_cloud"] = str(dst)
                artifact_meta["point_cloud"] = {
                    "source": "point_cloud",
                    "ext": dst.suffix.lower(),
                }
                logger.info("Prepared point cloud artifact: %s", dst)
            else:
                logger.warning("Point cloud requested but not available in WebODM outputs")

        logger.info(
            "Photogrammetry conversion finished: converted=%s",
            sorted(converted.keys()),
        )
        return converted, artifact_meta

    async def _upload_outputs(self, converted: Dict[str, str]) -> Dict[str, str]:
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
        uploaded: Dict[str, str],
        artifact_meta: Optional[Dict[str, Dict[str, Any]]] = None,
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
                db.add(
                    Asset(
                        model_id=model_id,
                        type=asset_type,
                        url=url,
                        meta_data={
                            "job_id": job_id,
                            "artifact_key": key,
                            **artifact_meta.get(key, {}),
                        },
                    )
                )
            await db.commit()
        logger.info(
            "Registered %s assets for model_id=%s (job_id=%s)",
            len(uploaded),
            model_id,
            job_id,
        )

    async def _update_job(
        self,
        job_id: int,
        *,
        processor_task_id: Optional[str] = None,
        progress: Optional[int] = None,
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
                job.finished_at = datetime.now(timezone.utc)
            if model:
                model.status = "ready"
            await db.commit()
        logger.info("Marked mapping job ready: job_id=%s model_id=%s", job_id, model_id)

    async def _mark_failed(self, job_id: int, error: str | None) -> None:
        async with Session() as db:
            job = await db.get(MappingJob, job_id)
            if not job:
                return
            job.status = "failed"
            job.error = error
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
        logger.error("Marked mapping job failed: job_id=%s error=%s", job_id, error)
