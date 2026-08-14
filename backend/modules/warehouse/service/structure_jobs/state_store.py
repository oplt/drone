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

from .constants import EXTRACTION_TASK_NAME, _EXTRACTION_CELERY_PROBE_AT, _EXTRACTION_STATE, _EXTRACTION_STATE_TTL_S

def _extraction_state_key(warehouse_map_id: int) -> str:
    return f"{_EXTRACTION_STATE_KEY_PREFIX}:{int(warehouse_map_id)}"

def _shared_state_get(warehouse_map_id: int) -> dict[str, Any] | None:
    try:
        raw = get_sync_redis_client().get(_extraction_state_key(warehouse_map_id))
        if raw:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
    except Exception:
        logger.debug("warehouse_structure_state_read_failed", exc_info=True)
    return None

def _shared_state_set(warehouse_map_id: int, state: dict[str, Any]) -> None:
    try:
        get_sync_redis_client().setex(
            _extraction_state_key(warehouse_map_id),
            _EXTRACTION_STATE_TTL_S,
            json.dumps(state, separators=(",", ":"), default=str),
        )
    except Exception:
        logger.debug("warehouse_structure_state_write_failed", exc_info=True)

def _shared_state_delete(warehouse_map_id: int) -> None:
    try:
        get_sync_redis_client().delete(_extraction_state_key(warehouse_map_id))
    except Exception:
        logger.debug("warehouse_structure_state_delete_failed", exc_info=True)

def record_extraction_queued(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    task_id: str | None = None,
    source: str = "api",
) -> dict[str, Any]:
    state = {
        "status": "queued",
        "warehouse_map_id": int(warehouse_map_id),
        "model_id": int(model_id),
        "client_flight_id": str(client_flight_id),
        "task_id": task_id,
        "source": source,
        "requested_at": datetime.now(UTC).isoformat(),
        "error_message": None,
    }
    _shared_state_set(int(warehouse_map_id), state)
    _EXTRACTION_STATE.set(int(warehouse_map_id), dict(state))
    return state

def record_extraction_running(*, warehouse_map_id: int) -> None:
    state = _shared_state_get(int(warehouse_map_id)) or (
        _EXTRACTION_STATE.get(int(warehouse_map_id)) or {}
    )
    state["status"] = "running"
    state["started_at"] = datetime.now(UTC).isoformat()
    _shared_state_set(int(warehouse_map_id), state)
    _EXTRACTION_STATE.set(int(warehouse_map_id), dict(state))

def record_extraction_ready(*, warehouse_map_id: int, target_count: int) -> None:
    _shared_state_delete(int(warehouse_map_id))
    _EXTRACTION_STATE.pop(int(warehouse_map_id))

def record_extraction_failed(
    *,
    warehouse_map_id: int,
    error_message: str,
    failure_reason_codes: list[str] | None = None,
    debug_artifact_url: str | None = None,
) -> None:
    state = _shared_state_get(int(warehouse_map_id)) or (
        _EXTRACTION_STATE.get(int(warehouse_map_id)) or {}
    )
    state["status"] = "failed"
    state["error_message"] = str(error_message or "Structure extraction failed.")[:2000]
    state["failure_reason_codes"] = list(failure_reason_codes or [])
    state["debug_artifact_url"] = debug_artifact_url
    state["finished_at"] = datetime.now(UTC).isoformat()
    _shared_state_set(int(warehouse_map_id), state)
    _EXTRACTION_STATE.set(int(warehouse_map_id), dict(state))

def _celery_probe_interval_s() -> float:
    from backend.core.config.runtime import settings

    return max(
        0.5,
        float(getattr(settings, "structure_extraction_celery_probe_interval_s", 3.0)),
    )

def get_extraction_state(warehouse_map_id: int) -> dict[str, Any] | None:
    state = _shared_state_get(int(warehouse_map_id)) or _EXTRACTION_STATE.get(int(warehouse_map_id))
    if state is None:
        return None
    task_id = state.get("task_id")
    if not task_id:
        return dict(state)
    raw_status = str(state.get("status") or "queued")
    now = time.monotonic()
    last_probe = _EXTRACTION_CELERY_PROBE_AT.get(int(warehouse_map_id)) or 0.0
    if raw_status not in {"queued", "running"} or (now - last_probe) < _celery_probe_interval_s():
        return dict(state)
    try:
        from celery.result import AsyncResult

        from backend.entrypoints.workers.celery_app import celery_app

        result = AsyncResult(str(task_id), app=celery_app)
        celery_state = str(result.state or "").upper()
        if celery_state in {"PENDING", "RECEIVED", "RETRY"}:
            state = {**state, "status": "queued"}
        elif celery_state == "STARTED":
            state = {**state, "status": "running"}
        elif celery_state == "SUCCESS":
            state = {**state, "status": "ready"}
        elif celery_state in {"FAILURE", "REVOKED"}:
            state = {
                **state,
                "status": "failed",
                "error_message": str(result.result or state.get("error_message") or "failed"),
            }
        _EXTRACTION_CELERY_PROBE_AT.set(int(warehouse_map_id), now)
    except Exception:
        logger.debug("structure_extraction_status_probe_failed", exc_info=True)
    _shared_state_set(int(warehouse_map_id), state)
    _EXTRACTION_STATE.set(int(warehouse_map_id), state)
    return dict(state)
