from __future__ import annotations

import asyncio
import os

from backend.tasks.celery_app import celery_app
from backend.services.photogrammetry.service import PhotogrammetryService


PHOTOGRAMMETRY_QUEUE = os.getenv("CELERY_PHOTOGRAMMETRY_QUEUE", "photogrammetry")


@celery_app.task(bind=True, name="photogrammetry.process_job", queue=PHOTOGRAMMETRY_QUEUE)
def process_photogrammetry_job(self, job_id: int) -> dict:
    """
    Runs:
      1) WebODM task creation + monitor
      2) downloads outputs
      3) converts to COG + 3D Tiles
      4) publishes assets, updates DB
    """
    async def _run():
        svc = PhotogrammetryService()
        return await svc.process_job(job_id=job_id, progress_cb=lambda p: self.update_state(state="PROGRESS", meta=p))
    return asyncio.run(_run())
