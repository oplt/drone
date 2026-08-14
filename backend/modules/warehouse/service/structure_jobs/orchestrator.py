"""Async orchestration for warehouse structure extraction."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import asdict
from typing import Any

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.warehouse.models import WarehouseCoordinateFrame
from backend.modules.warehouse.service.live_map_readiness import refresh_structure_input_readiness
from backend.modules.warehouse.service.occupancy_grid_parser import occupancy_grid_from_ros_yaml
from backend.modules.warehouse.service.structure_extraction import (
    StructureExtractionParams,
    extract_structure_from_flight,
)
from backend.observability.profiling import profile_stage

from .artifacts import _debug_payload, _safe_debug_value, _write_debug_artifact
from .failure_codes import (
    _failure_reason_codes_from_message,
    _quality_failure_reason_codes,
    _record_extraction_failure_metrics,
)
from .flight_resolution import resolve_latest_model_flight
from .manifest_hints import _attach_manifest_hints
from .persist import _persist_result
from .quality import (
    _attach_quality_gate,
    _force_review_without_clearance_evidence,
    _record_result_observability,
)
from .repository import update_durable_extraction_job
from .state_store import record_extraction_failed, record_extraction_ready, record_extraction_running
from .validation import (
    _validate_extraction_coordinate_frame,
    _validate_landmark_frame,
    _validate_manifest_coverage,
)

logger = logging.getLogger(__name__)


async def extract_and_persist_structure(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    params: StructureExtractionParams | None = None,
    extraction_job_id: int | None = None,
) -> dict[str, Any]:
    """Run structure extraction for a flight and persist targets + asset."""
    record_extraction_running(warehouse_map_id=int(warehouse_map_id))
    async with Session() as state_db:
        await update_durable_extraction_job(
            state_db,
            warehouse_map_id=int(warehouse_map_id),
            model_id=int(model_id),
            status="processing",
            job_id=extraction_job_id,
            progress=10,
        )
        await state_db.commit()
    effective = (params or StructureExtractionParams()).sanitized()
    try:
        coordinate_frame_id: int | None = None
        landmark_validation: dict[str, Any] | None = None
        async with Session() as db:
            coordinate_frame = (
                await db.execute(
                    select(WarehouseCoordinateFrame)
                    .where(
                        WarehouseCoordinateFrame.warehouse_map_id == int(warehouse_map_id),
                        WarehouseCoordinateFrame.status == "locked",
                    )
                    .order_by(WarehouseCoordinateFrame.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if coordinate_frame is None:
            raise RuntimeError("Structure extraction requires a locked warehouse coordinate frame")
        _validate_extraction_coordinate_frame(coordinate_frame)
        async with Session() as db:
            landmark_validation = await _validate_landmark_frame(
                db,
                warehouse_map_id=int(warehouse_map_id),
                coordinate_frame=coordinate_frame,
            )
        coordinate_frame_id = int(coordinate_frame.id)
        await asyncio.to_thread(_validate_manifest_coverage, client_flight_id, effective)
        readiness = await refresh_structure_input_readiness(timeout_s=8.0)
        live_occupancy = occupancy_grid_from_ros_yaml(readiness.occupancy_message)
        logger.info(
            "warehouse_structure_extract_readiness",
            extra={"warehouse_map_id": int(warehouse_map_id), **readiness.to_dict()},
        )
        with profile_stage("warehouse.structure_extraction", workload="production"):
            result = await asyncio.to_thread(
                extract_structure_from_flight,
                client_flight_id,
                params=effective,
                occupancy_grid=live_occupancy,
                odom_to_warehouse_map_transform=coordinate_frame.transform_json,
            )
        _attach_manifest_hints(result, client_flight_id)
        result.summary["diagnostics"] = {
            **readiness.to_dict(),
            "occupancy_snapshot_source": (
                "live_ros" if live_occupancy is not None else "saved_or_geometry_fallback"
            ),
            "worker_ros_env_ok": bool(readiness.esdf_available or readiness.occupancy_available),
        }
        result.summary["landmark_frame_validation"] = landmark_validation or {}
        _force_review_without_clearance_evidence(result)
        _attach_quality_gate(result)
        _record_result_observability(result)
        persisted = await _persist_result(
            warehouse_map_id=warehouse_map_id,
            model_id=model_id,
            client_flight_id=client_flight_id,
            result=result,
            coordinate_frame_id=int(coordinate_frame.id),
        )
        record_extraction_ready(
            warehouse_map_id=int(warehouse_map_id),
            target_count=int(persisted.get("target_count") or 0),
        )
        async with Session() as state_db:
            await update_durable_extraction_job(
                state_db,
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                status="ready",
                job_id=extraction_job_id,
                progress=100,
                confidence=persisted.get("confidence"),
                failure_reason_codes=list(persisted.get("failure_reason_codes") or []),
            )
            await state_db.commit()
        logger.info(
            "warehouse_coordinate_setup_detection_completed",
            extra={
                "warehouse_map_id": int(warehouse_map_id),
                **persisted,
                "quality_reasons": persisted.get("quality_reasons", []),
            },
        )
        return persisted
    except Exception as exc:
        failure_reason_codes = _failure_reason_codes_from_message(str(exc))
        _record_extraction_failure_metrics(failure_reason_codes)
        failure_checksum = hashlib.sha256(
            json.dumps(
                {
                    "warehouse_map_id": int(warehouse_map_id),
                    "model_id": int(model_id),
                    "client_flight_id": client_flight_id,
                    "error": str(exc),
                    "params": asdict(effective),
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        debug_path, debug_url = await asyncio.to_thread(
            _write_debug_artifact,
            client_flight_id,
            payload=_debug_payload(
                warehouse_map_id=warehouse_map_id,
                model_id=model_id,
                client_flight_id=client_flight_id,
                coordinate_frame_id=locals().get("coordinate_frame_id"),
                result=None,
                lineage_checksum=failure_checksum,
                failure_reason_codes=failure_reason_codes,
                error_message=str(exc),
            ),
            lineage_checksum=failure_checksum,
        )
        logger.warning(
            "warehouse_structure_detection_failed",
            extra={
                "warehouse_map_id": int(warehouse_map_id),
                "model_id": int(model_id),
                "client_flight_id": client_flight_id,
                "failure_reason_codes": failure_reason_codes,
                "debug_artifact_url": debug_url,
                "debug_artifact_path": str(debug_path) if debug_path else None,
            },
        )
        record_extraction_failed(
            warehouse_map_id=int(warehouse_map_id),
            error_message=str(exc),
            failure_reason_codes=failure_reason_codes,
            debug_artifact_url=debug_url,
        )
        async with Session() as state_db:
            await update_durable_extraction_job(
                state_db,
                warehouse_map_id=int(warehouse_map_id),
                model_id=int(model_id),
                status="failed",
                job_id=extraction_job_id,
                error=str(exc),
                progress=100,
                failure_reason_codes=failure_reason_codes,
            )
            await state_db.commit()
        raise


async def dry_run_structure_extraction(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    params: StructureExtractionParams | None = None,
) -> dict[str, Any]:
    """Run extraction without writing layout/targets/assets.

    This is intentionally read-only from the database perspective. It still
    writes a downloadable debug artifact next to the flight chunks so operators
    can inspect why the run is not publishable.
    """
    effective = (params or StructureExtractionParams()).sanitized()
    coordinate_frame_id: int | None = None
    landmark_validation: dict[str, Any] | None = None
    try:
        async with Session() as db:
            coordinate_frame = (
                await db.execute(
                    select(WarehouseCoordinateFrame)
                    .where(
                        WarehouseCoordinateFrame.warehouse_map_id == int(warehouse_map_id),
                        WarehouseCoordinateFrame.status == "locked",
                    )
                    .order_by(WarehouseCoordinateFrame.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if coordinate_frame is None:
            raise RuntimeError("Structure extraction requires a locked warehouse coordinate frame")
        _validate_extraction_coordinate_frame(coordinate_frame)
        async with Session() as db:
            landmark_validation = await _validate_landmark_frame(
                db,
                warehouse_map_id=int(warehouse_map_id),
                coordinate_frame=coordinate_frame,
            )
        coordinate_frame_id = int(coordinate_frame.id)
        await asyncio.to_thread(_validate_manifest_coverage, client_flight_id, effective)
        readiness = await refresh_structure_input_readiness(timeout_s=8.0)
        live_occupancy = occupancy_grid_from_ros_yaml(readiness.occupancy_message)
        result = await asyncio.to_thread(
            extract_structure_from_flight,
            client_flight_id,
            params=effective,
            occupancy_grid=live_occupancy,
            odom_to_warehouse_map_transform=coordinate_frame.transform_json,
        )
        _attach_manifest_hints(result, client_flight_id)
        result.summary["diagnostics"] = {
            **readiness.to_dict(),
            "occupancy_snapshot_source": (
                "live_ros" if live_occupancy is not None else "saved_or_geometry_fallback"
            ),
            "worker_ros_env_ok": bool(readiness.esdf_available or readiness.occupancy_available),
        }
        result.summary["landmark_frame_validation"] = landmark_validation or {}
        _force_review_without_clearance_evidence(result)
        _attach_quality_gate(result)
        _record_result_observability(result)
        failure_reason_codes = _quality_failure_reason_codes(result.summary)
        checksum = hashlib.sha256(
            json.dumps(
                {
                    "warehouse_map_id": int(warehouse_map_id),
                    "model_id": int(model_id),
                    "client_flight_id": client_flight_id,
                    "coordinate_frame_id": coordinate_frame_id,
                    "params": asdict(effective),
                    "summary": result.summary,
                },
                sort_keys=True,
                default=_safe_debug_value,
            ).encode()
        ).hexdigest()
        debug_path, debug_url = await asyncio.to_thread(
            _write_debug_artifact,
            client_flight_id,
            payload=_debug_payload(
                warehouse_map_id=warehouse_map_id,
                model_id=model_id,
                client_flight_id=client_flight_id,
                coordinate_frame_id=coordinate_frame_id,
                result=result,
                lineage_checksum=checksum,
                failure_reason_codes=failure_reason_codes,
            ),
            lineage_checksum=checksum,
        )
        quality = result.summary.get("quality")
        quality = quality if isinstance(quality, dict) else {}
        counts = result.summary.get("counts")
        counts = counts if isinstance(counts, dict) else {}
        return {
            "status": quality.get("status") or result.summary.get("status") or "needs_review",
            "warehouse_map_id": int(warehouse_map_id),
            "model_id": int(model_id),
            "client_flight_id": client_flight_id,
            "coordinate_frame_id": coordinate_frame_id,
            "target_count": int(counts.get("candidate_targets") or counts.get("targets") or 0),
            "active_target_count": int(counts.get("active_targets") or 0),
            "review_target_count": int(counts.get("review_targets") or 0),
            "rejected_target_count": int(counts.get("rejected_clearance") or 0),
            "quality_status": quality.get("status"),
            "quality_reasons": list(quality.get("reasons") or []),
            "failure_reason_codes": failure_reason_codes,
            "confidence": quality.get("confidence"),
            "debug_artifact_url": debug_url,
            "debug_artifact_path": str(debug_path) if debug_path else None,
            "summary": result.summary,
        }
    except Exception as exc:
        failure_reason_codes = _failure_reason_codes_from_message(str(exc))
        _record_extraction_failure_metrics(failure_reason_codes)
        checksum = hashlib.sha256(
            json.dumps(
                {
                    "warehouse_map_id": int(warehouse_map_id),
                    "model_id": int(model_id),
                    "client_flight_id": client_flight_id,
                    "error": str(exc),
                    "params": asdict(effective),
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        debug_path, debug_url = await asyncio.to_thread(
            _write_debug_artifact,
            client_flight_id,
            payload=_debug_payload(
                warehouse_map_id=warehouse_map_id,
                model_id=model_id,
                client_flight_id=client_flight_id,
                coordinate_frame_id=coordinate_frame_id,
                result=None,
                lineage_checksum=checksum,
                failure_reason_codes=failure_reason_codes,
                error_message=str(exc),
            ),
            lineage_checksum=checksum,
        )
        return {
            "status": "failed",
            "warehouse_map_id": int(warehouse_map_id),
            "model_id": int(model_id),
            "client_flight_id": client_flight_id,
            "coordinate_frame_id": coordinate_frame_id,
            "target_count": 0,
            "active_target_count": 0,
            "review_target_count": 0,
            "rejected_target_count": 0,
            "quality_status": "failed",
            "quality_reasons": [],
            "failure_reason_codes": failure_reason_codes,
            "confidence": None,
            "debug_artifact_url": debug_url,
            "debug_artifact_path": str(debug_path) if debug_path else None,
            "error_message": str(exc),
            "summary": {},
        }
