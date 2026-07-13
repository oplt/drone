from __future__ import annotations

import logging

from backend.core.config.runtime import settings
from backend.infrastructure.jobs import enqueue_task

logger = logging.getLogger(__name__)


class MappingJobQueueError(RuntimeError):
    """Raised when a mapping job cannot be enqueued."""


class MappingJobQueue:
    """
    Queue adapter for heavy photogrammetry jobs.

    Photogrammetry processing must run on worker nodes, not in the API process.
    """

    def __init__(self) -> None:
        self.backend = settings.MAPPING_JOB_QUEUE_BACKEND.strip().lower()

    def enqueue(self, *, job_id: int) -> str:
        if self.backend != "celery":
            raise MappingJobQueueError(
                f"Unsupported MAPPING_JOB_QUEUE_BACKEND='{self.backend}'. "
                "Use 'celery' for Redis-backed worker processing."
            )

        try:
            from backend.observability.instruments import observed_span

            with observed_span(
                "job.enqueue",
                job_name="photogrammetry.process_job",
                queue="photogrammetry",
            ):
                task_id = enqueue_task(
                    "photogrammetry.process_job",
                    queue=settings.CELERY_PHOTOGRAMMETRY_QUEUE,
                    job_id=job_id,
                )
        except Exception as exc:
            raise MappingJobQueueError(
                "Failed to enqueue mapping job. Ensure Redis broker and Celery workers are running."
            ) from exc

        logger.info("Enqueued photogrammetry job job_id=%s task_id=%s", job_id, task_id)
        return task_id
