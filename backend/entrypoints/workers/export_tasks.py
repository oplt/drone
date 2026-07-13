from __future__ import annotations

import asyncio

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.deliverables.export_job import run_mission_export


@celery_app.task(
    queue="exports",
    bind=True,
    max_retries=3,
    name="backend.tasks.export_tasks.generate_mission_export",
    soft_time_limit=180,
    time_limit=240,
)
def generate_mission_export(
    self, flight_id: str, user_id: int, org_id: int | None, job_id: int
) -> None:
    try:
        asyncio.run(run_mission_export(flight_id, user_id, org_id, job_id))
    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries),
        ) from exc
