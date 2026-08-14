from __future__ import annotations

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.irrigation.worker_service import (
    IrrigationJobRetry,
    run_irrigation_monitor_tick,
)
from backend.modules.irrigation.worker_service import (
    process_irrigation_job as process_irrigation_job_service,
)
from backend.shared.worker_idempotency import (
    WorkerTaskClaim,
    claim_worker_task,
    complete_worker_task,
    release_worker_task,
)

IRRIGATION_MAX_RETRIES = 2
_worker_loop = WorkerLoopState()
# process_mission execution is delegated to the irrigation application service.


@celery_app.task(
    bind=True,
    max_retries=IRRIGATION_MAX_RETRIES,
    name="irrigation.process_job",
    time_limit=1800,
    soft_time_limit=1500,
)
def process_irrigation_job(self, job_id: str) -> dict[str, str]:
    claim, cached = claim_worker_task("irrigation", job_id, ttl_s=7200)
    if claim == WorkerTaskClaim.SKIP_COMPLETED and cached is not None:
        return cached  # type: ignore[return-value]
    if claim == WorkerTaskClaim.SKIP_IN_FLIGHT:
        return {"job_id": job_id, "status": "duplicate"}
    try:
        result = _worker_loop.run(
            process_irrigation_job_service(
                job_id, retry_count=self.request.retries, max_retries=IRRIGATION_MAX_RETRIES
            )
        )
        status = result.get("status")
        if status == "completed":
            complete_worker_task("irrigation", job_id, result, ttl_s=7200)
        elif status != "missing":
            release_worker_task("irrigation", job_id)
        return result
    except IrrigationJobRetry as exc:
        release_worker_task("irrigation", job_id)
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(
                attempt=self.request.retries,
                max_seconds=300,
            ),
        ) from exc
    except Exception:
        release_worker_task("irrigation", job_id)
        raise


@celery_app.task(
    name="irrigation.monitor_tick",
    queue="default",
    time_limit=120,
    soft_time_limit=90,
)
def monitor_irrigation_jobs() -> dict[str, str]:
    _worker_loop.run(run_irrigation_monitor_tick())
    return {"status": "completed"}
