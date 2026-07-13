from __future__ import annotations

import logging

from backend.core.config.runtime import settings
from backend.infrastructure.jobs import enqueue_task

logger = logging.getLogger(__name__)


class VideoAnalysisQueueError(RuntimeError):
    pass


class VideoAnalysisQueue:
    def enqueue(self, *, job_id: str) -> str:
        try:
            task_id = enqueue_task(
                "video_analysis.process_job",
                queue=settings.celery_video_analysis_queue,
                job_id=job_id,
            )
        except Exception as exc:
            raise VideoAnalysisQueueError("Failed to enqueue video analysis.") from exc

        logger.info("Enqueued video analysis job job_id=%s task_id=%s", job_id, task_id)
        return task_id
