from __future__ import annotations

import asyncio

from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.deliverables.job import DeliverableGenerationJob


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
        asyncio.run(DeliverableGenerationJob().run(deliverable_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30) from exc
