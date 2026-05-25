from __future__ import annotations

import asyncio

from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.automation.scheduling_job import dispatch_due_templates, execute_scheduled_run


@celery_app.task(
    queue="scheduling",
    bind=True,
    max_retries=3,
    name="backend.tasks.scheduling_tasks.run_template_mission",
    soft_time_limit=120,
    time_limit=180,
)
def run_template_mission(self, scheduled_run_id: int) -> None:
    try:
        asyncio.run(execute_scheduled_run(scheduled_run_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30) from exc


@celery_app.task(name="backend.tasks.scheduling_tasks.check_due_templates")
def check_due_templates() -> None:
    asyncio.run(dispatch_due_templates(run_template_mission.delay))
