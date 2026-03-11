from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import threading
from typing import Any, Coroutine

from backend.tasks.celery_app import celery_app
from backend.config import setup_logging
from backend.db.repository.settings_repo import SettingsRepository
from backend.services.photogrammetry.service import PhotogrammetryService
from backend.utils.config_runtime import get_runtime_settings


logger = logging.getLogger(__name__)
setup_logging()
PHOTOGRAMMETRY_QUEUE = os.getenv("CELERY_PHOTOGRAMMETRY_QUEUE", "photogrammetry")
ENABLE_NATIVE_ASYNC_TASK = os.getenv("CELERY_ENABLE_NATIVE_ASYNC_TASK", "0").lower() in {
    "1",
    "true",
    "yes",
}
if ENABLE_NATIVE_ASYNC_TASK and importlib.util.find_spec("celery_aio_pool") is None:
    logger.warning(
        "CELERY_ENABLE_NATIVE_ASYNC_TASK=1 requested, but celery_aio_pool is not installed. "
        "Falling back to prefork-compatible async loop reuse mode."
    )
    ENABLE_NATIVE_ASYNC_TASK = False

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
    await get_runtime_settings(SettingsRepository())
    svc = PhotogrammetryService()

    def _progress_cb(progress: dict) -> None:
        task.update_state(state="PROGRESS", meta=progress)

    return await svc.process_job(
        job_id=job_id,
        progress_cb=_progress_cb,
    )


if ENABLE_NATIVE_ASYNC_TASK:

    @celery_app.task(bind=True, name="photogrammetry.process_job", queue=PHOTOGRAMMETRY_QUEUE)
    async def process_photogrammetry_job(self, job_id: int) -> dict:
        """
        Native async Celery task mode (requires async-capable worker pool).
        """
        return await _run_photogrammetry_pipeline(self, job_id)

else:

    @celery_app.task(bind=True, name="photogrammetry.process_job", queue=PHOTOGRAMMETRY_QUEUE)
    def process_photogrammetry_job(self, job_id: int) -> dict:
        """
        Prefork-compatible mode: reuse a thread-local event loop in the worker thread.
        """
        return _run_on_worker_loop(_run_photogrammetry_pipeline(self, job_id))
