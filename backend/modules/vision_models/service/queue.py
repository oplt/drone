from __future__ import annotations

from backend.infrastructure.jobs import enqueue_task
from backend.infrastructure.jobs.celery_queue import QueueEnqueueError
from backend.modules.vision_models.config import vision_settings


class VisionTrainingQueueError(RuntimeError):
    pass


class VisionTrainingQueue:
    def enqueue(self, run_id: str) -> str:
        try:
            return enqueue_task(
                "vision_models.train",
                queue=vision_settings.celery_vision_training_queue,
                run_id=run_id,
            )
        except QueueEnqueueError as exc:
            raise VisionTrainingQueueError("Training worker is unavailable") from exc

    def revoke(self, task_id: str) -> None:
        from backend.entrypoints.workers.celery_app import celery_app

        celery_app.control.revoke(task_id, terminate=False)
