"""Warehouse mapping Celery tasks.

Currently hosts the post-flight *structure extraction* job: once a warehouse 3D
map is ready, this converts the saved point-cloud into aisles/racks/shelves/bins
and writes ``WarehouseScanTarget`` rows + a ``STRUCTURE_MAP`` asset. It runs in
the dedicated ``warehouse-mapping`` queue so the heavy CPU work never touches the
API event loop or the in-flight scan path.
"""

from __future__ import annotations

import logging
import os
import socket
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
    get_extraction_state,
    params_from_payload,
    record_mapping_worker_heartbeat,
)
from backend.shared.worker_idempotency import (
    WorkerTaskClaim,
    claim_worker_task,
    complete_worker_task,
    release_worker_task,
)

logger = logging.getLogger(__name__)
setup_logging()

WAREHOUSE_MAPPING_QUEUE = settings.celery_warehouse_mapping_queue
_worker_loop = WorkerLoopState()
_TASK_NAME = EXTRACTION_TASK_NAME


def _extraction_idempotency_key(
    *,
    warehouse_map_id: int,
    model_id: int,
    extraction_job_id: int | None,
) -> str:
    if extraction_job_id is not None:
        return f"job:{int(extraction_job_id)}"
    return f"map:{int(warehouse_map_id)}:model:{int(model_id)}"


def _cached_extraction_result(existing_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ready",
        "warehouse_map_id": existing_state.get("warehouse_map_id"),
        "model_id": existing_state.get("model_id"),
        "target_count": existing_state.get("target_count"),
        "duplicate": True,
    }


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


@celery_app.task(
    bind=True,
    max_retries=1,
    name=EXTRACTION_TASK_NAME,
    queue=WAREHOUSE_MAPPING_QUEUE,
    time_limit=3600,
    soft_time_limit=3300,
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
    idempotency_key = _extraction_idempotency_key(
        warehouse_map_id=int(warehouse_map_id),
        model_id=int(model_id),
        extraction_job_id=extraction_job_id,
    )
    claim, cached = claim_worker_task("warehouse_extract", idempotency_key, ttl_s=7200)
    if claim == WorkerTaskClaim.SKIP_COMPLETED and cached is not None:
        return cached
    if claim == WorkerTaskClaim.SKIP_IN_FLIGHT:
        return {
            "status": "duplicate",
            "warehouse_map_id": int(warehouse_map_id),
            "model_id": int(model_id),
        }
    existing_state = get_extraction_state(int(warehouse_map_id)) or {}
    if existing_state.get("status") == "ready":
        cached_result = _cached_extraction_result(existing_state)
        complete_worker_task("warehouse_extract", idempotency_key, cached_result, ttl_s=7200)
        return cached_result
    try:
        result = _worker_loop.run(
            extract_and_persist_structure(
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                client_flight_id=str(client_flight_id),
                params=params_from_payload(params),
                extraction_job_id=extraction_job_id,
            )
        )
        complete_worker_task("warehouse_extract", idempotency_key, result, ttl_s=7200)
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
            record_extraction_failed(
                warehouse_map_id=int(warehouse_map_id),
                error_message=str(exc),
                failure_reason_codes=list(existing_state.get("failure_reason_codes") or []),
                debug_artifact_url=existing_state.get("debug_artifact_url"),
            )
            release_worker_task("warehouse_extract", idempotency_key)
        else:
            release_worker_task("warehouse_extract", idempotency_key)
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries),
        ) from exc
