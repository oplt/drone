from __future__ import annotations
import asyncio
from celery import shared_task
from backend.services.photogrammetry.mission import PhotogrammetryService

@shared_task(bind=True, name="photogrammetry.process_job")
def process_photogrammetry_job(self, job_id: str) -> dict:
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