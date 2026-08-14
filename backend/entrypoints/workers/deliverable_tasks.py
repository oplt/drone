from __future__ import annotations

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.deliverables.job import DeliverableGenerationJob

_worker_loop = WorkerLoopState()


@celery_app.task(
    queue="exports",
    bind=True,
    max_retries=3,
    name="backend.tasks.deliverable_tasks.generate_field_deliverable",
    soft_time_limit=120,
    time_limit=180,
)
def generate_field_deliverable(self, deliverable_id: int) -> None:
    try:
        _worker_loop.run(DeliverableGenerationJob().run(deliverable_id))
    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries),
        ) from exc
