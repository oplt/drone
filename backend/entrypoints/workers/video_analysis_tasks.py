from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Coroutine
from typing import Any

from backend.core.config.runtime import settings, setup_logging
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.video_analysis.service.pipeline import run_video_analysis_job

logger = logging.getLogger(__name__)
setup_logging()
VIDEO_ANALYSIS_QUEUE = settings.celery_video_analysis_queue
_loop_lock = threading.Lock()
_thread_local_state = threading.local()


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    loop = getattr(_thread_local_state, "loop", None)
    if loop is not None and not loop.is_closed():
        return loop
    with _loop_lock:
        loop = getattr(_thread_local_state, "loop", None)
        if loop is not None and not loop.is_closed():
            return loop
        loop = asyncio.new_event_loop()
        _thread_local_state.loop = loop
        return loop


def _run_on_worker_loop(coro: Coroutine[Any, Any, dict[str, str]]) -> dict[str, str]:
    loop = _get_worker_loop()
    if loop.is_running():
        raise RuntimeError("Video analysis worker event loop is already running.")
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(
    bind=True,
    max_retries=2,
    name="video_analysis.process_job",
    queue=VIDEO_ANALYSIS_QUEUE,
)
def process_video_analysis_job(self, job_id: str) -> dict[str, str]:
    logger.info("Starting video analysis task job_id=%s", job_id)
    try:
        result = _run_on_worker_loop(run_video_analysis_job(job_id))
        logger.info("Completed video analysis task job_id=%s", job_id)
        return result
    except Exception as exc:
        logger.exception("Video analysis task failed job_id=%s", job_id)
        raise self.retry(exc=exc, countdown=30) from exc
