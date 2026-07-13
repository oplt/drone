from __future__ import annotations

from backend.core.config.runtime import settings
from backend.infrastructure.jobs import enqueue_task


class IrrigationQueueError(RuntimeError):
    pass


def enqueue_irrigation_processing(job_id: str) -> str:
    try:
        return enqueue_task(
            "irrigation.process_job",
            queue=settings.celery_default_queue,
            job_id=job_id,
        )
    except Exception as exc:
        raise IrrigationQueueError("Failed to enqueue irrigation processing") from exc
