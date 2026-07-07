from __future__ import annotations

import asyncio
import importlib.util
import logging
from collections.abc import Coroutine
from typing import Any

from backend.core.config.runtime import env_truthy, settings, setup_logging
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.infrastructure.mapping import build_mapping_job

logger = logging.getLogger(__name__)
setup_logging()
PHOTOGRAMMETRY_QUEUE = settings.CELERY_PHOTOGRAMMETRY_QUEUE
ENABLE_NATIVE_ASYNC_TASK = env_truthy(settings.celery_enable_native_async_task)
if ENABLE_NATIVE_ASYNC_TASK and importlib.util.find_spec("celery_aio_pool") is None:
    logger.warning(
        "CELERY_ENABLE_NATIVE_ASYNC_TASK=1 requested, but celery_aio_pool is not installed. "
        "Falling back to prefork-compatible async loop reuse mode."
    )
    ENABLE_NATIVE_ASYNC_TASK = False

_worker_loop = WorkerLoopState()


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    return _worker_loop.get_loop()


def _run_on_worker_loop(coro: Coroutine[Any, Any, dict]) -> dict:
    loop = _get_worker_loop()
    if loop.is_running():
        raise RuntimeError(
            "Celery sync fallback loop is already running. "
            "Enable CELERY_ENABLE_NATIVE_ASYNC_TASK=1 with an async-capable worker pool."
        )
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _run_photogrammetry_pipeline(task, job_id: int) -> dict:
    def _progress_cb(progress: dict) -> None:
        task.update_state(state="PROGRESS", meta=progress)

    return await build_mapping_job().run(
        job_id=job_id,
        progress_cb=_progress_cb,
    )


if ENABLE_NATIVE_ASYNC_TASK:

    @celery_app.task(
        bind=True,
        max_retries=3,
        name="photogrammetry.process_job",
        queue=PHOTOGRAMMETRY_QUEUE,
    )
    async def process_photogrammetry_job(self, job_id: int) -> dict:
        """
        Native async Celery task mode (requires async-capable worker pool).
        """
        try:
            return await _run_photogrammetry_pipeline(self, job_id)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=30) from exc

else:

    @celery_app.task(
        bind=True,
        max_retries=3,
        name="photogrammetry.process_job",
        queue=PHOTOGRAMMETRY_QUEUE,
    )
    def process_photogrammetry_job(self, job_id: int) -> dict:
        """
        Prefork-compatible mode: reuse a thread-local event loop in the worker thread.
        """
        try:
            return _run_on_worker_loop(_run_photogrammetry_pipeline(self, job_id))
        except Exception as exc:
            raise self.retry(exc=exc, countdown=30) from exc
