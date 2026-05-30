from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class WarehouseMappingQueueError(RuntimeError):
    pass


class WarehouseMappingQueue:
    def __init__(self) -> None:
        self.backend = os.getenv("MAPPING_JOB_QUEUE_BACKEND", "celery").strip().lower()

    def enqueue(self, *, job_id: int) -> str:
        if self.backend != "celery":
            raise WarehouseMappingQueueError(
                f"Unsupported MAPPING_JOB_QUEUE_BACKEND='{self.backend}'. Use 'celery'."
            )
        try:
            from backend.entrypoints.workers.warehouse_mapping_tasks import (
                process_warehouse_mapping_job,
            )

            result = process_warehouse_mapping_job.delay(job_id=job_id)
        except Exception as exc:
            raise WarehouseMappingQueueError(
                "Failed to enqueue warehouse mapping job. Check Celery broker/worker."
            ) from exc
        task_id = getattr(result, "id", None)
        if not task_id:
            raise WarehouseMappingQueueError("Queue backend did not return a task id.")
        logger.info("Enqueued warehouse mapping job job_id=%s task_id=%s", job_id, task_id)
        return str(task_id)
