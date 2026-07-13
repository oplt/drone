"""Warehouse mapping Celery tasks.

Currently hosts the post-flight *structure extraction* job: once a warehouse 3D
map is ready, this converts the saved point-cloud into aisles/racks/shelves/bins
and writes ``WarehouseScanTarget`` rows + a ``STRUCTURE_MAP`` asset. It runs in
the dedicated ``warehouse-mapping`` queue so the heavy CPU work never touches the
API event loop or the in-flight scan path.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Coroutine
from typing import Any

from celery.signals import heartbeat_sent, worker_ready, worker_shutdown

from backend.core.config.runtime import settings, setup_logging
from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.warehouse.service.structure_jobs import (
    EXTRACTION_TASK_NAME,
    extract_and_persist_structure,
    record_extraction_failed,
    clear_mapping_worker_heartbeat,
    params_from_payload,
    record_mapping_worker_heartbeat,
)

logger = logging.getLogger(__name__)
setup_logging()

WAREHOUSE_MAPPING_QUEUE = settings.celery_warehouse_mapping_queue
_worker_loop = WorkerLoopState()
_TASK_NAME = EXTRACTION_TASK_NAME


@worker_ready.connect
def _verify_warehouse_mapping_tasks_registered(sender: Any = None, **_kwargs: Any) -> None:
    worker_name = str(getattr(sender, "hostname", f"warehouse-mapping@{socket.gethostname()}"))
    record_mapping_worker_heartbeat(worker_name)
    logger.info(
        "warehouse_mapping_worker_ros_env",
        extra={
            "ros_distro": os.getenv("ROS_DISTRO"),
            "ros_domain_id": os.getenv("ROS_DOMAIN_ID"),
            "ament_prefix_path_present": bool(os.getenv("AMENT_PREFIX_PATH")),
            "ros_workspace_sourced": "ros2_ws/install" in os.getenv("AMENT_PREFIX_PATH", ""),
        },
    )
    if _TASK_NAME not in celery_app.tasks:
        logger.error(
            "warehouse_mapping worker boot: task %s is NOT registered; "
            "auto-detect will discard extraction jobs until the worker restarts.",
            _TASK_NAME,
        )
        return
    logger.info("warehouse_mapping worker boot: registered task %s", _TASK_NAME)


@heartbeat_sent.connect
def _warehouse_mapping_worker_heartbeat(sender: Any = None, **_kwargs: Any) -> None:
    name = str(getattr(sender, "hostname", "warehouse-mapping-worker"))
    record_mapping_worker_heartbeat(name)


@worker_shutdown.connect
def _warehouse_mapping_worker_shutdown(sender: Any = None, **_kwargs: Any) -> None:
    name = str(getattr(sender, "hostname", "warehouse-mapping-worker"))
    clear_mapping_worker_heartbeat(name)


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    return _worker_loop.get_loop()


def _run_on_worker_loop(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    loop = _get_worker_loop()
    if loop.is_running():
        raise RuntimeError("Warehouse mapping worker event loop is already running.")
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(
    bind=True,
    max_retries=1,
    name=EXTRACTION_TASK_NAME,
    queue=WAREHOUSE_MAPPING_QUEUE,
)
def extract_warehouse_structure(
    self,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    params: dict[str, Any] | None = None,
    extraction_job_id: int | None = None,
) -> dict[str, Any]:
    logger.info(
        "Starting warehouse structure extraction map_id=%s model_id=%s flight=%s",
        warehouse_map_id,
        model_id,
        client_flight_id,
    )
    try:
        result = _run_on_worker_loop(
            extract_and_persist_structure(
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                client_flight_id=str(client_flight_id),
                params=params_from_payload(params),
                extraction_job_id=extraction_job_id,
            )
        )
        logger.info(
            "Completed warehouse structure extraction map_id=%s targets=%s",
            warehouse_map_id,
            result.get("target_count"),
        )
        return result
    except Exception as exc:
        logger.exception(
            "Warehouse structure extraction failed map_id=%s flight=%s",
            warehouse_map_id,
            client_flight_id,
        )
        if self.request.retries >= self.max_retries:
            from backend.modules.warehouse.service.structure_jobs import get_extraction_state

            existing_state = get_extraction_state(int(warehouse_map_id)) or {}
            record_extraction_failed(
                warehouse_map_id=int(warehouse_map_id),
                error_message=str(exc),
                failure_reason_codes=list(existing_state.get("failure_reason_codes") or []),
                debug_artifact_url=existing_state.get("debug_artifact_url"),
            )
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries),
        ) from exc
