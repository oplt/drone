from __future__ import annotations

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.automation.scheduling_job import dispatch_due_templates, execute_scheduled_run

_worker_loop = WorkerLoopState()


@celery_app.task(
    queue="scheduling",
    bind=True,
    max_retries=3,
    name="backend.tasks.scheduling_tasks.run_template_mission",
    soft_time_limit=3_600,
    time_limit=3_660,
)
def run_template_mission(self, scheduled_run_id: int) -> None:
    try:
        _worker_loop.run(execute_scheduled_run(scheduled_run_id))
    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries),
        ) from exc


@celery_app.task(
    queue="scheduling",
    name="backend.tasks.scheduling_tasks.check_due_templates",
    soft_time_limit=60,
    time_limit=90,
)
def check_due_templates() -> None:
    _worker_loop.run(dispatch_due_templates(run_template_mission.delay))
