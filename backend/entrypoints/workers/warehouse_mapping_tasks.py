from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Coroutine
from typing import Any, cast

from backend.core.config.runtime import setup_logging
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.warehouse.service.mapping import (
    WarehouseScanMappingError,
    WarehouseScanMappingPreconditionError,
    WarehouseScanMappingService,
)

logger = logging.getLogger(__name__)
setup_logging()

WAREHOUSE_MAPPING_QUEUE = os.getenv("CELERY_WAREHOUSE_MAPPING_QUEUE", "warehouse-mapping")
_loop_lock = threading.Lock()
_thread_local_state = threading.local()


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    loop = getattr(_thread_local_state, "loop", None)
    if loop is not None and not loop.is_closed():
        return cast(asyncio.AbstractEventLoop, loop)
    with _loop_lock:
        loop = getattr(_thread_local_state, "loop", None)
        if loop is not None and not loop.is_closed():
            return cast(asyncio.AbstractEventLoop, loop)
        loop = asyncio.new_event_loop()
        _thread_local_state.loop = loop
        return loop


def _run_on_worker_loop(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    loop = _get_worker_loop()
    if loop.is_running():
        raise RuntimeError("Celery warehouse mapping loop is already running.")
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(  # type: ignore[misc]
    bind=True,
    max_retries=3,
    name="warehouse_mapping.process_job",
    queue=WAREHOUSE_MAPPING_QUEUE,
)
def process_warehouse_mapping_job(self: Any, job_id: int) -> dict[str, Any]:
    try:
        return _run_on_worker_loop(WarehouseScanMappingService().process_job(job_id=job_id))
    except WarehouseScanMappingPreconditionError as exc:
        logger.error(
            "Warehouse mapping job %s failed precondition (no retry): %s",
            job_id,
            exc,
        )
        return {"job_id": job_id, "status": "failed_precondition", "error": str(exc)}
    except WarehouseScanMappingError as exc:
        logger.error("Warehouse mapping job %s failed: %s", job_id, exc)
        return {"job_id": job_id, "status": "failed", "error": str(exc)}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30) from exc
