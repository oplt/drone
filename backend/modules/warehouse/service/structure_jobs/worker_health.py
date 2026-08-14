"""Structure job module."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, select

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.infrastructure.cache.local import BoundedTTLCache
from backend.infrastructure.cache.redis import get_sync_redis_client, redis_available
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseCoordinateFrame,
    WarehouseDockStation,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
    WarehouseScanArtifactSet,
    WarehouseScanTarget,
    WarehouseSensorRig,
)
from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
    record_inspection_target_clearance_failure,
    record_low_confidence_candidate,
    record_structure_extraction_failure,
)
from backend.modules.warehouse.schemas import WarehouseLocalPose, WarehouseSensorAim
from backend.modules.warehouse.service.drift_guard import (
    transform_checksum,
    validate_localization_evidence,
)
from backend.modules.warehouse.service.gazebo_landmark_consistency import (
    LandmarkObservation,
    LandmarkSpec,
    evaluate_landmark_consistency,
)
from backend.modules.warehouse.service.layout import create_extracted_layout
from backend.modules.warehouse.service.live_map_manifest import load_flight_manifest
from backend.modules.warehouse.service.live_map_readiness import (
    refresh_structure_input_readiness,
)
from backend.modules.warehouse.service.live_map_storage import (
    warehouse_live_map_chunk_storage,
)
from backend.modules.warehouse.service.occupancy_grid_parser import (
    occupancy_grid_from_ros_yaml,
)
from backend.modules.warehouse.service.scan_to_layout import (
    CandidateInput,
    extraction_confidence,
    persist_candidates,
)
from backend.modules.warehouse.service.structure_extraction import (
    StructureExtractionParams,
    StructureResult,
    extract_structure_from_flight,
)
from backend.observability.profiling import profile_stage

logger = logging.getLogger(__name__)

from .constants import EXTRACTION_TASK_NAME, _WORKER_HEARTBEAT_PREFIX, _WORKER_READY_KEY
from .deps import resolve_worker_ready_cache, set_worker_ready_cache

def record_mapping_worker_heartbeat(worker_name: str, *, ttl_s: int = 15) -> None:
    try:
        get_sync_redis_client().setex(
            f"{_WORKER_HEARTBEAT_PREFIX}:{worker_name}",
            max(5, int(ttl_s)),
            str(datetime.now(UTC).timestamp()),
        )
    except Exception:
        logger.debug("warehouse_worker_heartbeat_write_failed", exc_info=True)

def clear_mapping_worker_heartbeat(worker_name: str) -> None:
    try:
        get_sync_redis_client().delete(f"{_WORKER_HEARTBEAT_PREFIX}:{worker_name}")
    except Exception:
        logger.debug("warehouse_worker_heartbeat_delete_failed", exc_info=True)

def warehouse_mapping_worker_ready(*, force: bool = False) -> tuple[bool, str | None]:
    """Return whether a warehouse-mapping worker has the extract task registered."""
    from backend.core.config.runtime import settings

    ttl = max(1.0, float(getattr(settings, "warehouse_mapping_worker_probe_cache_ttl_s", 20.0)))
    now = time.monotonic()
    if not force:
        try:
            raw = get_sync_redis_client().get(_WORKER_READY_KEY)
            if raw:
                shared = json.loads(raw)
                if isinstance(shared, dict) and (now - float(shared.get("checked_at", 0.0))) < ttl:
                    return bool(shared.get("ready")), shared.get("detail")
        except Exception:
            logger.debug("warehouse_worker_readiness_shared_state_read_failed", exc_info=True)
    worker_ready_cache = resolve_worker_ready_cache()
    if not force and worker_ready_cache is not None:
        cached_at, ready, detail = worker_ready_cache
        if (now - cached_at) < ttl:
            return ready, detail

    def _finish(ready: bool, detail: str | None) -> tuple[bool, str | None]:
        set_worker_ready_cache((now, ready, detail))
        try:
            get_sync_redis_client().setex(
                _WORKER_READY_KEY,
                max(1, int(ttl)),
                json.dumps({"checked_at": now, "ready": ready, "detail": detail}),
            )
        except Exception:
            logger.debug("warehouse_worker_readiness_shared_state_write_failed", exc_info=True)
        return ready, detail

    try:
        from backend.entrypoints.workers.celery_app import celery_app

        if EXTRACTION_TASK_NAME not in celery_app.tasks:
            return _finish(
                False,
                "Structure extraction task is not registered in this API process. "
                "Restart the dev stack with `make warehouse`.",
            )
        inspect = celery_app.control.inspect(timeout=0.75)
        queues_by_worker = inspect.active_queues() or {}
        registered_by_worker = inspect.registered() or {}
    except Exception:
        logger.debug("warehouse_mapping_worker_probe_failed", exc_info=True)
        return _finish(False, "Could not reach Celery workers.")
    if not queues_by_worker:
        return _finish(
            False,
            "No Celery workers are running. Start `warehouse_mapping_worker` via `make warehouse`.",
        )

    queue_name = settings.celery_warehouse_mapping_queue
    workers_on_queue: list[str] = []
    workers_missing_task: list[str] = []
    workers_without_heartbeat: list[str] = []
    shared_heartbeat_available = redis_available()
    for worker_name, queues in queues_by_worker.items():
        if not any(queue.get("name") == queue_name for queue in queues or []):
            continue
        workers_on_queue.append(worker_name)
        worker_tasks = set(registered_by_worker.get(worker_name) or [])
        if EXTRACTION_TASK_NAME not in worker_tasks:
            workers_missing_task.append(worker_name)
        elif shared_heartbeat_available:
            try:
                heartbeat_key = f"{_WORKER_HEARTBEAT_PREFIX}:{worker_name}"
                if not get_sync_redis_client().exists(heartbeat_key):
                    workers_without_heartbeat.append(worker_name)
            except Exception:
                shared_heartbeat_available = False

    if not workers_on_queue:
        return _finish(
            False,
            f"No worker is consuming the `{queue_name}` queue. "
            "Start `warehouse_mapping_worker` via `make warehouse`.",
        )
    if workers_missing_task:
        return _finish(
            False,
            "Warehouse mapping worker is running but has not loaded "
            f"`{EXTRACTION_TASK_NAME}`. Restart with `make warehouse` to pick up new code.",
        )
    if workers_without_heartbeat:
        return _finish(
            False,
            "Warehouse mapping worker is registered but its heartbeat lease is stale. "
            "Wait for the worker heartbeat or restart it.",
        )
    return _finish(True, None)
