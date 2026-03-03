from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from datetime import datetime
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
                    else:
                        raise RuntimeError(
                            "No input images found for mapping job. "
                            "Upload images or use input_source='drone_sync'."
                        )

                job.status = "processing"
                job.progress = 1
                job.started_at = datetime.utcnow()
                model.status = "processing"
                await db.commit()

            task_id = await self.webodm.create_task(
                job_id=job_id,
                options=webodm_options,
                image_paths=[str(p) for p in uploaded_images],
            )
            await self._update_job(job_id, processor_task_id=task_id, progress=5)

            while True:
                status = await self.webodm.get_task_status(task_id)
                progress = int(status.get("progress", 0))
                if progress_cb:
                    progress_cb({"progress": progress})

                if status["state"] == "COMPLETED":
                    await self._update_job(job_id, progress=55)
                    break
                if status["state"] == "FAILED":
                    error_msg = status.get("error") or "WebODM task failed"
                    await self._mark_failed(job_id, error_msg)
                    raise RuntimeError(error_msg)
                await asyncio.sleep(5)

            outputs = await self.webodm.download_outputs(task_id)
            await self._update_job(job_id, progress=65)
            download_root = outputs.get("__download_root")
            if "__download_root" in outputs:
                outputs = {k: v for k, v in outputs.items() if k != "__download_root"}

            with tempfile.TemporaryDirectory(prefix=f"mapping-job-{job_id}-") as tmp_dir:
                work = Path(tmp_dir)
                converted, artifact_meta = self._convert_outputs(
                    outputs,
                    work,
                    requested_artifacts=requested_artifacts,
                )
                await self._update_job(job_id, progress=80)

                uploaded = await self._upload_outputs(converted)
                await self._update_job(job_id, progress=90)

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

        if ortho_enabled:
            ortho_src = outputs.get("orthophoto")
            if not ortho_src:
                raise RuntimeError("WebODM output missing required orthophoto")
            ortho_cog = convert_to_cog(ortho_src, str(work_dir / "orthomosaic.cog.tif"))
            converted["orthomosaic_cog"] = ortho_cog
            artifact_meta["orthomosaic_cog"] = {
                "georef": inspect_raster_georeferencing(ortho_cog),
                "source": "orthophoto",
            }

        if dsm_enabled:
            dsm_src = outputs.get("dsm")
            if not dsm_src:
                raise RuntimeError("WebODM output missing required DSM")
            dsm_cog = convert_to_cog(dsm_src, str(work_dir / "dsm.cog.tif"))
            converted["dsm_cog"] = dsm_cog
            artifact_meta["dsm_cog"] = {
                "georef": inspect_raster_georeferencing(dsm_cog),
                "source": "dsm",
            }

        if dtm_enabled:
            dtm_src = outputs.get("dtm")
            if dtm_src:
                dtm_cog = convert_to_cog(dtm_src, str(work_dir / "dtm.cog.tif"))
                converted["dtm_cog"] = dtm_cog
                artifact_meta["dtm_cog"] = {
                    "georef": inspect_raster_georeferencing(dtm_cog),
                    "source": "dtm",
                }
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

        if mesh_enabled:
            mesh_src = outputs.get("mesh")
            if not mesh_src:
                raise RuntimeError("WebODM output missing required mesh")
            tileset_dir = convert_mesh_to_3dtiles(mesh_src, str(work_dir / "mesh_3dtiles"))
            converted["textured_mesh_3dtiles"] = tileset_dir
            artifact_meta["textured_mesh_3dtiles"] = {
                "source": "mesh",
                "format": "3dtiles",
            }

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
            else:
                logger.warning("Point cloud requested but not available in WebODM outputs")

        return converted, artifact_meta

    async def _upload_outputs(self, converted: Dict[str, str]) -> Dict[str, str]:
        uploaded: Dict[str, str] = {}
        for key, path in converted.items():
            src = Path(path)
            if src.is_dir():
                uploaded[key] = await self.storage.upload_directory(str(src))
            else:
                uploaded[key] = await self.storage.upload_file(str(src))
        return uploaded

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
                job.finished_at = datetime.utcnow()
            if model:
                model.status = "ready"
            await db.commit()

    async def _mark_failed(self, job_id: int, error: str | None) -> None:
        async with Session() as db:
            job = await db.get(MappingJob, job_id)
            if not job:
                return
            job.status = "failed"
            job.error = error
            job.finished_at = datetime.utcnow()
            await db.commit()
