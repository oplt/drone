from __future__ import annotations

import asyncio

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.irrigation.worker_service import (
    IrrigationJobRetry,
    run_irrigation_monitor_tick,
)
from backend.modules.irrigation.worker_service import (
    process_irrigation_job as process_irrigation_job_service,
)

IRRIGATION_MAX_RETRIES = 2
# process_mission execution is delegated to the irrigation application service.


@celery_app.task(bind=True, max_retries=IRRIGATION_MAX_RETRIES, name="irrigation.process_job")
def process_irrigation_job(self, job_id: str) -> dict[str, str]:
    try:
        return asyncio.run(
            process_irrigation_job_service(
                job_id, retry_count=self.request.retries, max_retries=IRRIGATION_MAX_RETRIES
            )
        )
    except IrrigationJobRetry as exc:
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(
                attempt=self.request.retries,
                max_seconds=300,
            ),
        ) from exc


@celery_app.task(name="irrigation.monitor_tick", queue="default")
def monitor_irrigation_jobs() -> dict[str, str]:
    asyncio.run(run_irrigation_monitor_tick())
    return {"status": "completed"}
