from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from backend.core.config.runtime import setup_logging
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.vision_models.config import vision_settings
from backend.modules.vision_models.service.training_service import VisionTrainingService

logger = logging.getLogger(__name__)
setup_logging()
_worker_loop = WorkerLoopState()


def _run_on_worker_loop(coro: Coroutine[Any, Any, dict[str, str]]) -> dict[str, str]:
    loop = _worker_loop.get_loop()
    if loop.is_running():
        raise RuntimeError("Vision training worker event loop is already running")
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(
    name="vision_models.train",
    queue=vision_settings.celery_vision_training_queue,
    time_limit=vision_settings.celery_vision_training_time_limit_seconds,
    soft_time_limit=vision_settings.celery_vision_training_soft_time_limit_seconds,
)
def train_vision_model(run_id: str) -> dict[str, str]:
    logger.info("Starting vision training task run_id=%s", run_id)
    result = _run_on_worker_loop(VisionTrainingService().run(run_id))
    logger.info("Finished vision training task run_id=%s", run_id)
    return result
