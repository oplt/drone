from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from backend.core.config.runtime import setup_logging
from backend.core.database.session import Session
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.vision_models.config import vision_settings
from backend.modules.vision_models.repository import VisionRepository
from backend.modules.vision_models.service.training_service import (
    VisionTrainingService,
    reconcile_stale_training_runs,
)

logger = logging.getLogger(__name__)
setup_logging()
_worker_loop = WorkerLoopState()


def _run_on_worker_loop(coro: Coroutine[Any, Any, Any]) -> Any:
    loop = _worker_loop.get_loop()
    if loop.is_running():
        raise RuntimeError("Vision training worker event loop is already running")
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(
    bind=True,
    name="vision_models.train",
    queue=vision_settings.celery_vision_training_queue,
    time_limit=vision_settings.celery_vision_training_time_limit_seconds,
    soft_time_limit=vision_settings.celery_vision_training_soft_time_limit_seconds,
)
def train_vision_model(self, run_id: str) -> dict[str, str]:
    logger.info("Starting vision training task run_id=%s", run_id)
    result = _run_on_worker_loop(
        VisionTrainingService().run(run_id, lease_owner=str(self.request.id))
    )
    logger.info("Finished vision training task run_id=%s", run_id)
    return result


@celery_app.task(
    name="vision_models.reconcile_stale_training_runs",
    queue=vision_settings.celery_vision_training_queue,
)
def reconcile_stale_vision_training_runs() -> dict[str, int]:
    count = _run_on_worker_loop(reconcile_stale_training_runs())
    return {"reconciled": int(count)}


async def _reconcile_staged_storage_objects() -> int:
    async with Session() as db:
        return await VisionRepository(db).reconcile_staged_storage_objects(
            older_than_minutes=vision_settings.vision_staged_object_max_age_minutes
        )


@celery_app.task(
    name="vision_models.reconcile_staged_storage_objects",
    queue=vision_settings.celery_vision_training_queue,
)
def reconcile_staged_vision_storage_objects() -> dict[str, int]:
    count = _run_on_worker_loop(_reconcile_staged_storage_objects())
    return {"reconciled": int(count)}
