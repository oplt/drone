from __future__ import annotations

import logging

from backend.core.config.runtime import settings, setup_logging
from backend.core.database.session import Session
from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.video_analysis.service.pipeline import run_video_analysis_job

logger = logging.getLogger(__name__)
setup_logging()
VIDEO_ANALYSIS_QUEUE = settings.celery_video_analysis_queue
VIDEO_ANALYSIS_TIME_LIMIT_SECONDS = settings.celery_video_analysis_time_limit_seconds
VIDEO_ANALYSIS_SOFT_TIME_LIMIT_SECONDS = settings.celery_video_analysis_soft_time_limit_seconds
_worker_loop = WorkerLoopState()


@celery_app.task(
    bind=True,
    max_retries=2,
    name="video_analysis.process_job",
    queue=VIDEO_ANALYSIS_QUEUE,
    time_limit=VIDEO_ANALYSIS_TIME_LIMIT_SECONDS,
    soft_time_limit=VIDEO_ANALYSIS_SOFT_TIME_LIMIT_SECONDS,
)
def process_video_analysis_job(self, job_id: str) -> dict[str, str]:
    logger.info("Starting video analysis task job_id=%s", job_id)
    try:
        result = _worker_loop.run(run_video_analysis_job(job_id))
        if result.get("status") in {"completed", "failed", "cancelled"}:
            celery_app.send_task(
                "agriculture.video_inference_completed",
                kwargs={"job_id": job_id, "status": result["status"]},
                queue=settings.celery_agriculture_inference_queue,
            )
        logger.info("Completed video analysis task job_id=%s", job_id)
        return result
    except Exception as exc:
        logger.exception("Video analysis task failed job_id=%s", job_id)
        if self.request.retries >= self.max_retries:
            celery_app.send_task(
                "agriculture.video_inference_completed",
                kwargs={"job_id": job_id, "status": "failed"},
                queue=settings.celery_agriculture_inference_queue,
            )
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries),
        ) from exc


async def _reconcile_stale_video_jobs() -> dict[str, int]:
    async with Session() as db:
        reconciled = await VideoAnalysisRepository(db).reconcile_stale_jobs()
    return {"reconciled": reconciled}


@celery_app.task(
    name="video_analysis.reconcile_stale_jobs",
    queue=VIDEO_ANALYSIS_QUEUE,
    time_limit=300,
    soft_time_limit=240,
)
def reconcile_stale_video_jobs() -> dict[str, int]:
    return _worker_loop.run(_reconcile_stale_video_jobs())


async def _reconcile_staged_storage_objects() -> dict[str, int]:
    async with Session() as db:
        reconciled = await VideoAnalysisRepository(db).reconcile_staged_storage_objects(
            older_than_minutes=settings.video_analysis_staged_object_max_age_minutes
        )
    return {"reconciled": reconciled}


@celery_app.task(
    name="video_analysis.reconcile_staged_storage_objects",
    queue=VIDEO_ANALYSIS_QUEUE,
    time_limit=300,
    soft_time_limit=240,
)
def reconcile_staged_storage_objects() -> dict[str, int]:
    return _worker_loop.run(_reconcile_staged_storage_objects())
