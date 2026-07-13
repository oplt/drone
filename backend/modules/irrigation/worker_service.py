"""Application service for irrigation background processing.

Celery entrypoints stay transport-only; database/session and domain work live here.
"""

from __future__ import annotations

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.irrigation.job_repository import IrrigationJobRepository
from backend.modules.irrigation.models import IrrigationProcessingJob
from backend.modules.irrigation.monitor import IrrigationMonitor
from backend.modules.irrigation.service.processing import irrigation_service
from backend.modules.missions.runtime_models import MissionRuntime


class IrrigationJobRetry(Exception):
    """Transient processing failure; the Celery adapter decides retry policy."""


async def process_irrigation_job(
    job_id: str,
    *,
    retry_count: int,
    max_retries: int,
) -> dict[str, str]:
    repository = IrrigationJobRepository()
    async with Session() as db:
        job = await db.get(IrrigationProcessingJob, job_id)
        if job is None:
            return {"job_id": job_id, "status": "missing"}
        if job.status == "completed" and not job.force:
            return {"job_id": job_id, "status": "completed"}
        await repository.mark_started(db, job_id)
        try:
            mission = await db.scalar(
                select(MissionRuntime).where(MissionRuntime.client_flight_id == job.mission_id)
            )
            if mission is None:
                raise ValueError("Irrigation mission not found")
            await irrigation_service.process_mission(db, mission=mission, force=job.force)
        except Exception as exc:
            if retry_count < max_retries:
                await repository.mark_retrying(db, job_id, error=str(exc))
                raise IrrigationJobRetry(str(exc)) from exc
            await repository.mark_finished(db, job_id, status="failed", error=str(exc))
            raise
        await repository.mark_finished(db, job_id, status="completed")
        return {"job_id": job_id, "status": "completed"}


async def run_irrigation_monitor_tick() -> None:
    await IrrigationMonitor()._tick()
