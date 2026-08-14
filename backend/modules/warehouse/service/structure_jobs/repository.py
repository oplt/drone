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

from .constants import STRUCTURE_EXTRACTION_ALGORITHM_VERSION

async def create_durable_extraction_job(
    db,
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    params: dict[str, Any] | None = None,
) -> WarehouseMappingJob:
    """Create/reuse the PostgreSQL extraction job used for recovery/polling."""
    payload = dict(params or {})
    payload["client_flight_id"] = str(client_flight_id)
    input_checksum = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    payload["input_checksum"] = input_checksum
    candidates = (
        await db.execute(
            select(WarehouseMappingJob)
            .where(
                WarehouseMappingJob.warehouse_map_id == int(warehouse_map_id),
                WarehouseMappingJob.model_id == int(model_id),
                WarehouseMappingJob.processor == "warehouse_structure",
                WarehouseMappingJob.status.in_(("queued", "processing")),
            )
            .order_by(WarehouseMappingJob.id.desc())
            .limit(10)
        )
    ).scalars().all()
    for existing in candidates:
        existing_params = existing.params if isinstance(existing.params, dict) else {}
        if existing_params.get("input_checksum") == input_checksum:
            return existing
    job = WarehouseMappingJob(
        warehouse_map_id=int(warehouse_map_id),
        model_id=int(model_id),
        status="queued",
        progress=0,
        processor="warehouse_structure",
        algorithm_version=STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
        input_checksum=input_checksum,
        extraction_params=payload,
        params=payload,
    )
    db.add(job)
    await db.flush()
    return job

async def update_durable_extraction_job(
    db,
    *,
    warehouse_map_id: int,
    model_id: int,
    status: str,
    job_id: int | None = None,
    task_id: str | None = None,
    error: str | None = None,
    progress: int | None = None,
    confidence: float | None = None,
    failure_reason_codes: list[str] | None = None,
) -> None:
    statement = (
        select(WarehouseMappingJob)
        .where(
            WarehouseMappingJob.warehouse_map_id == int(warehouse_map_id),
            WarehouseMappingJob.model_id == int(model_id),
            WarehouseMappingJob.processor == "warehouse_structure",
        )
    )
    if job_id is not None:
        statement = statement.where(WarehouseMappingJob.id == int(job_id))
    job = (
        await db.execute(
            statement
            .order_by(WarehouseMappingJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        return
    job.status = str(status)
    if task_id:
        job.processor_task_id = str(task_id)
    if error is not None:
        job.error = str(error)[:2000]
    if progress is not None:
        job.progress = max(0, min(100, int(progress)))
    if confidence is not None:
        job.confidence = max(0.0, min(1.0, float(confidence)))
    if failure_reason_codes is not None:
        job.failure_reason_codes = [str(code)[:128] for code in failure_reason_codes[:32]]
    now = datetime.now(UTC)
    if status == "processing" and job.started_at is None:
        job.started_at = now
    if status in {"ready", "failed"}:
        job.finished_at = now
    await db.flush()

async def get_durable_extraction_state(db, warehouse_map_id: int) -> dict[str, Any] | None:
    job = (
        await db.execute(
            select(WarehouseMappingJob)
            .where(
                WarehouseMappingJob.warehouse_map_id == int(warehouse_map_id),
                WarehouseMappingJob.processor == "warehouse_structure",
            )
            .order_by(WarehouseMappingJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    return {
        "status": str(job.status),
        "warehouse_map_id": int(job.warehouse_map_id),
        "model_id": int(job.model_id),
        "task_id": job.processor_task_id,
        "error_message": job.error,
        "progress": int(job.progress or 0),
        "algorithm_version": job.algorithm_version,
        "input_checksum": job.input_checksum,
        "extraction_params": job.extraction_params,
        "confidence": job.confidence,
        "failure_reason_codes": list(job.failure_reason_codes or []),
        "requested_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
