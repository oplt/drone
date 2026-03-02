# backend/services/photogrammetry/service.py

from __future__ import annotations
import asyncio
from typing import Callable, Optional

from backend.db.session import SessionLocal
from backend.db.models import MappingJob, FieldModel, Asset
from backend.services.photogrammetry.webodm_client import WebODMClient
from backend.services.photogrammetry.tiling import (
    convert_to_cog,
    convert_mesh_to_3dtiles,
)
from backend.services.photogrammetry.storage import StorageService


class PhotogrammetryService:
    """
    Orchestrates full photogrammetry processing pipeline.
    Called from Celery worker.
    """

    def __init__(self):
        self.webodm = WebODMClient()
        self.storage = StorageService()

    async def process_job(
        self,
        *,
        job_id: str,
        progress_cb: Optional[Callable[[dict], None]] = None,
    ) -> dict:

        async with SessionLocal() as db:
            job = await db.get(MappingJob, job_id)
            if not job:
                raise ValueError(f"MappingJob {job_id} not found")

            model = await db.get(FieldModel, job.model_id)

            job.status = "processing"
            await db.commit()

        # -----------------------------------------
        # 1) Submit to WebODM
        # -----------------------------------------

        task_id = await self.webodm.create_task(job_id=job_id)

        await self._update_processor_id(job_id, task_id)

        # -----------------------------------------
        # 2) Poll until done
        # -----------------------------------------

        while True:
            status = await self.webodm.get_task_status(task_id)

            if progress_cb:
                progress_cb({"progress": status["progress"]})

            if status["state"] == "COMPLETED":
                break
            if status["state"] == "FAILED":
                await self._mark_failed(job_id, status.get("error"))
                raise RuntimeError("WebODM task failed")

            await asyncio.sleep(5)

        # -----------------------------------------
        # 3) Download outputs
        # -----------------------------------------

        outputs = await self.webodm.download_outputs(task_id)

        ortho_path = outputs["orthophoto"]
        dsm_path = outputs["dsm"]
        mesh_path = outputs["mesh"]

        # -----------------------------------------
        # 4) Convert formats
        # -----------------------------------------

        cog_path = convert_to_cog(ortho_path)
        tileset_dir = convert_mesh_to_3dtiles(mesh_path)

        # -----------------------------------------
        # 5) Upload to storage
        # -----------------------------------------

        ortho_url = await self.storage.upload_file(cog_path)
        tileset_url = await self.storage.upload_directory(tileset_dir)

        # -----------------------------------------
        # 6) Register assets
        # -----------------------------------------

        async with SessionLocal() as db:
            asset_ortho = Asset(
                model_id=model.id,
                type="ORTHO_COG",
                url=ortho_url,
            )

            asset_tiles = Asset(
                model_id=model.id,
                type="TILESET_3D",
                url=tileset_url,
            )

            db.add_all([asset_ortho, asset_tiles])

            model.status = "ready"
            job.status = "ready"

            await db.commit()

        return {
            "status": "ready",
            "tileset_url": tileset_url,
        }

    # --------------------------------------------------

    async def _update_processor_id(self, job_id: str, task_id: str):
        async with SessionLocal() as db:
            job = await db.get(MappingJob, job_id)
            job.processor_task_id = task_id
            await db.commit()

    async def _mark_failed(self, job_id: str, error: str | None):
        async with SessionLocal() as db:
            job = await db.get(MappingJob, job_id)
            job.status = "failed"
            job.error = error
            await db.commit()