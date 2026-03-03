from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class MappingJobQueueError(RuntimeError):
    """Raised when a mapping job cannot be enqueued."""


class MappingJobQueue:
    """
    Queue adapter for heavy photogrammetry jobs.

    Photogrammetry processing must run on worker nodes, not in the API process.
    """

    def __init__(self) -> None:
        self.backend = os.getenv("MAPPING_JOB_QUEUE_BACKEND", "celery").strip().lower()

    def enqueue(self, *, job_id: int) -> str:
        if self.backend != "celery":
            raise MappingJobQueueError(
                f"Unsupported MAPPING_JOB_QUEUE_BACKEND='{self.backend}'. "
                "Use 'celery' for Redis-backed worker processing."
            )

        try:
            from backend.tasks.photogrammetry_tasks import process_photogrammetry_job

            result = process_photogrammetry_job.delay(job_id=job_id)
        except Exception as exc:
            raise MappingJobQueueError(
                "Failed to enqueue mapping job. Ensure Redis broker and Celery workers are running."
            ) from exc

        task_id = getattr(result, "id", None)
        if not task_id:
            raise MappingJobQueueError("Queue backend did not return a task id.")

        logger.info("Enqueued photogrammetry job job_id=%s task_id=%s", job_id, task_id)
        return task_id
