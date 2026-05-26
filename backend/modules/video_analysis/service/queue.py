from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class VideoAnalysisQueueError(RuntimeError):
    pass


class VideoAnalysisQueue:
    def enqueue(self, *, job_id: str) -> str:
        try:
            from backend.entrypoints.workers.video_analysis_tasks import process_video_analysis_job

            result = process_video_analysis_job.delay(job_id=job_id)
        except Exception as exc:
            raise VideoAnalysisQueueError("Failed to enqueue video analysis.") from exc

        task_id = getattr(result, "id", None)
        if not task_id:
            raise VideoAnalysisQueueError("Queue backend did not return a task id.")
        logger.info("Enqueued video analysis job job_id=%s task_id=%s", job_id, task_id)
        return task_id
