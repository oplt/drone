"""Async orchestration for warehouse structure extraction.

Bridges the pure-geometry :mod:`structure_extraction` module to the database:
runs the heavy CPU work in a worker thread, then (idempotently) replaces the
auto-generated ``WarehouseScanTarget`` rows for a model and writes a
``STRUCTURE_MAP`` asset the frontend can use to draw aisle/rack overlays.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, select

from backend.core.database.session import Session
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseCoordinateFrame,
    WarehouseMap,
    WarehouseModel,
    WarehouseScanArtifactSet,
    WarehouseScanTarget,
    WarehouseSensorRig,
)
from backend.modules.warehouse.schemas import WarehouseLocalPose, WarehouseSensorAim
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
from backend.modules.warehouse.service.scan_to_layout import CandidateInput, persist_candidates
from backend.modules.warehouse.service.structure_extraction import (
    StructureExtractionParams,
    StructureResult,
    extract_structure_from_flight,
)

logger = logging.getLogger(__name__)
STRUCTURE_EXTRACTION_ALGORITHM_VERSION = "warehouse-structure-v1"
_HASH_CHUNK_SIZE_BYTES = 1024 * 1024

STRUCTURE_ASSET_TYPE = "STRUCTURE_MAP"
EXTRACTION_TASK_NAME = "warehouse_mapping.extract_structure"

# In-process extraction job state keyed by warehouse_map_id. Survives API
# polling between enqueue (persist_capture or UI) and Celery completion.
_EXTRACTION_STATE: dict[int, dict[str, Any]] = {}
_EXTRACTION_CELERY_PROBE_AT: dict[int, float] = {}
_WORKER_READY_CACHE: tuple[float, bool, str | None] | None = None


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
    _EXTRACTION_STATE[int(warehouse_map_id)] = state
    return state


def record_extraction_running(*, warehouse_map_id: int) -> None:
    state = _EXTRACTION_STATE.setdefault(int(warehouse_map_id), {})
    state["status"] = "running"
    state["started_at"] = datetime.now(UTC).isoformat()


def record_extraction_ready(*, warehouse_map_id: int, target_count: int) -> None:
    _EXTRACTION_STATE.pop(int(warehouse_map_id), None)


def record_extraction_failed(*, warehouse_map_id: int, error_message: str) -> None:
    state = _EXTRACTION_STATE.setdefault(int(warehouse_map_id), {})
    state["status"] = "failed"
    state["error_message"] = str(error_message or "Structure extraction failed.")[:2000]
    state["finished_at"] = datetime.now(UTC).isoformat()


def _celery_probe_interval_s() -> float:
    from backend.core.config.runtime import settings

    return max(
        0.5,
        float(getattr(settings, "structure_extraction_celery_probe_interval_s", 3.0)),
    )


def get_extraction_state(warehouse_map_id: int) -> dict[str, Any] | None:
    state = _EXTRACTION_STATE.get(int(warehouse_map_id))
    if state is None:
        return None
    task_id = state.get("task_id")
    if not task_id:
        return dict(state)
    raw_status = str(state.get("status") or "queued")
    now = time.monotonic()
    last_probe = _EXTRACTION_CELERY_PROBE_AT.get(int(warehouse_map_id), 0.0)
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
        _EXTRACTION_CELERY_PROBE_AT[int(warehouse_map_id)] = now
    except Exception:
        logger.debug("structure_extraction_status_probe_failed", exc_info=True)
    _EXTRACTION_STATE[int(warehouse_map_id)] = state
    return dict(state)


def warehouse_mapping_worker_ready(*, force: bool = False) -> tuple[bool, str | None]:
    """Return whether a warehouse-mapping worker has the extract task registered."""
    global _WORKER_READY_CACHE
    from backend.core.config.runtime import settings

    ttl = max(1.0, float(getattr(settings, "warehouse_mapping_worker_probe_cache_ttl_s", 20.0)))
    now = time.monotonic()
    if not force and _WORKER_READY_CACHE is not None:
        cached_at, ready, detail = _WORKER_READY_CACHE
        if (now - cached_at) < ttl:
            return ready, detail

    def _finish(ready: bool, detail: str | None) -> tuple[bool, str | None]:
        global _WORKER_READY_CACHE
        _WORKER_READY_CACHE = (now, ready, detail)
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
    for worker_name, queues in queues_by_worker.items():
        if not any(queue.get("name") == queue_name for queue in queues or []):
            continue
        workers_on_queue.append(worker_name)
        worker_tasks = set(registered_by_worker.get(worker_name) or [])
        if EXTRACTION_TASK_NAME not in worker_tasks:
            workers_missing_task.append(worker_name)

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
    return _finish(True, None)


def _write_summary_asset(
    client_flight_id: str, summary: dict[str, Any], lineage_checksum: str
) -> Path | None:
    """Persist the structure summary JSON next to the flight chunks."""
    try:
        flight_dir = warehouse_live_map_chunk_storage.flight_dir(client_flight_id)
        flight_dir.mkdir(parents=True, exist_ok=True)
        path = flight_dir / f"structure_map-{lineage_checksum[:16]}.json"
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return path
    except OSError:
        logger.warning("structure_extraction: failed to write summary asset", exc_info=True)
        return None


def _hash_input_file(path: Path) -> tuple[int, str]:
    """Hash a potentially large scan input without loading it into memory."""
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_SIZE_BYTES):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Scan input changed while lineage was captured: {path}")
    return after.st_size, digest.hexdigest()


def _scan_artifact_lineage(
    client_flight_id: str,
    *,
    model_id: int,
    coordinate_frame_id: int,
    extraction_params: dict[str, Any],
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    flight_dir = warehouse_live_map_chunk_storage.flight_dir(client_flight_id)
    inputs: list[dict[str, Any]] = []
    if flight_dir.exists():
        for path in sorted(item for item in flight_dir.rglob("*") if item.is_file()):
            if path.name.startswith("structure_map"):
                continue
            size_bytes, digest = _hash_input_file(path)
            inputs.append(
                {
                    "path": str(path.relative_to(flight_dir)),
                    "size_bytes": size_bytes,
                    "checksum_sha256": digest,
                }
            )
    manifest = load_flight_manifest(client_flight_id)
    manifest_json = manifest.as_dict() if manifest is not None else {}
    lineage = {
        "client_flight_id": client_flight_id,
        "map_model_id": model_id,
        "coordinate_frame_id": coordinate_frame_id,
        "algorithm_version": STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
        "extraction_params": extraction_params,
        "manifest": manifest_json,
        "inputs": inputs,
    }
    checksum = hashlib.sha256(
        json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return checksum, manifest_json, inputs


async def _persist_result(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    result: StructureResult,
    coordinate_frame_id: int,
) -> dict[str, Any]:
    quality = result.summary.get("quality") if isinstance(result.summary, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    quality_status = str(quality.get("status") or "ready")
    active_target_count = sum(target.clearance_status == "active" for target in result.targets)
    review_target_count = sum(
        target.clearance_status == "needs_review" for target in result.targets
    )
    rejected_target_count = sum(target.clearance_status == "rejected" for target in result.targets)
    extraction_params = dict(result.summary.get("params") or {})
    lineage_checksum, manifest_json, inputs_json = await asyncio.to_thread(
        _scan_artifact_lineage,
        client_flight_id,
        model_id=int(model_id),
        coordinate_frame_id=int(coordinate_frame_id),
        extraction_params=extraction_params,
    )
    summary_path = await asyncio.to_thread(
        _write_summary_asset, client_flight_id, result.summary, lineage_checksum
    )

    async with Session() as db:
        try:
            model = await db.get(WarehouseModel, int(model_id))
            if model is None:
                raise RuntimeError(f"Warehouse model {model_id} was not found")
            model.coordinate_frame_id = int(coordinate_frame_id)
            warehouse_map = await db.get(WarehouseMap, int(warehouse_map_id))
            if warehouse_map is None:
                raise RuntimeError(f"Warehouse map {warehouse_map_id} was not found")
            rig_scope = (
                WarehouseSensorRig.org_id == warehouse_map.org_id
                if warehouse_map.org_id is not None
                else and_(
                    WarehouseSensorRig.org_id.is_(None),
                    WarehouseSensorRig.owner_id == warehouse_map.owner_id,
                )
            )
            sensor_rig = (
                await db.execute(
                    select(WarehouseSensorRig)
                    .where(
                        WarehouseSensorRig.active.is_(True),
                        WarehouseSensorRig.calibration_status == "valid",
                        WarehouseSensorRig.calibration_hash.is_not(None),
                        rig_scope,
                    )
                    .order_by(WarehouseSensorRig.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            artifact_set = (
                await db.execute(
                    select(WarehouseScanArtifactSet).where(
                        WarehouseScanArtifactSet.checksum_sha256 == lineage_checksum
                    )
                )
            ).scalar_one_or_none()
            if artifact_set is None:
                artifact_set = WarehouseScanArtifactSet(
                    warehouse_map_id=int(warehouse_map_id),
                    map_model_id=int(model_id),
                    coordinate_frame_id=int(coordinate_frame_id),
                    sensor_rig_id=int(sensor_rig.id) if sensor_rig is not None else None,
                    calibration_hash=(
                        sensor_rig.calibration_hash if sensor_rig is not None else None
                    ),
                    client_flight_id=client_flight_id,
                    checksum_sha256=lineage_checksum,
                    manifest_json=manifest_json,
                    inputs_json=inputs_json,
                    extraction_params_json=extraction_params,
                    algorithm_version=STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                )
                db.add(artifact_set)
                await db.flush()
            layout, bin_ids, published = await create_extracted_layout(
                db,
                warehouse_map_id=int(warehouse_map_id),
                coordinate_frame_id=int(coordinate_frame_id),
                map_model_id=int(model_id),
                artifact_set_id=int(artifact_set.id),
                input_checksum=lineage_checksum,
                algorithm_version=STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                targets=result.targets,
            )
            await persist_candidates(
                db,
                warehouse_map_id=int(warehouse_map_id),
                layout_version_id=int(layout.id),
                candidates=[
                    CandidateInput(
                        entity_kind="bin",
                        identity_key=(
                            f"{target.aisle_code}/{target.rack_code}/"
                            f"{target.shelf_level}/{target.bin_code}"
                        ),
                        geometry={"target_point": target.target_point},
                        confidence=float(
                            0.9
                            if target.clearance_status == "active"
                            else 0.55
                            if target.clearance_status == "needs_review"
                            else 0.25
                        ),
                    )
                    for target in result.targets
                ],
            )
            # Idempotent re-run: drop the previous auto-generated targets for this
            # model (identified by reference_model_id) while leaving operator-made
            # targets (reference_model_id NULL or other models) untouched.
            await db.execute(
                delete(WarehouseScanTarget).where(
                    WarehouseScanTarget.warehouse_map_id == int(warehouse_map_id),
                    WarehouseScanTarget.reference_model_id == int(model_id),
                    WarehouseScanTarget.provenance_status == "auto",
                )
            )

            for tgt in result.targets:
                scan_pose = WarehouseLocalPose.model_validate(tgt.scan_pose).model_dump()
                scan_pose["_clearance_status"] = tgt.clearance_status
                scan_pose["_clearance_m"] = tgt.clearance_m
                scan_pose["_clearance_source"] = tgt.clearance_source
                db.add(
                    WarehouseScanTarget(
                        warehouse_map_id=int(warehouse_map_id),
                        reference_model_id=int(model_id),
                        coordinate_frame_id=int(coordinate_frame_id),
                        layout_version_id=int(layout.id),
                        bin_id=bin_ids[
                            (
                                str(tgt.aisle_code),
                                str(tgt.rack_code),
                                int(tgt.shelf_level),
                                str(tgt.bin_code),
                            )
                        ],
                        aisle_code=tgt.aisle_code,
                        rack_code=tgt.rack_code,
                        shelf_level=tgt.shelf_level,
                        bin_code=tgt.bin_code,
                        target_point_local_json=tgt.target_point,
                        scan_pose_local_json=scan_pose,
                        sensor_aim_json=WarehouseSensorAim(
                            aim_point_local_json=tgt.target_point,
                            orientation=scan_pose["orientation"],
                        ).model_dump(),
                        shelf_normal_local_json=tgt.shelf_normal,
                        standoff_m=float(tgt.standoff_m),
                        priority=int(tgt.priority),
                        active=published and tgt.clearance_status == "active",
                        provenance_status="auto",
                    )
                )

            db.add(
                WarehouseAsset(
                    model_id=int(model_id),
                    coordinate_frame_id=int(coordinate_frame_id),
                    frame_id="warehouse_map",
                    type=STRUCTURE_ASSET_TYPE,
                    url=str(summary_path) if summary_path else f"memory://structure/{model_id}",
                    checksum=hashlib.sha256(
                        json.dumps(result.summary, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                    meta_data={
                        "warehouse_map_id": int(warehouse_map_id),
                        "coordinate_frame_id": int(coordinate_frame_id),
                        "artifact_set_id": int(artifact_set.id),
                        "input_checksum": lineage_checksum,
                        "algorithm_version": STRUCTURE_EXTRACTION_ALGORITHM_VERSION,
                        "layout_version_id": int(layout.id),
                        "layout_published": published,
                        "client_flight_id": client_flight_id,
                        "generated_at": datetime.now(UTC).isoformat(),
                        "summary": result.summary,
                        "target_count": len(result.targets),
                        "active_target_count": active_target_count,
                        "review_target_count": review_target_count,
                        "rejected_target_count": rejected_target_count,
                        "coordinate_setup_status": (
                            "active" if active_target_count > 0 else "draft"
                        ),
                        "manual_review_required": quality_status != "ready"
                        or review_target_count > 0,
                        "quality_status": quality_status,
                        "quality_reasons": list(quality.get("reasons") or []),
                        "confidence": quality.get("confidence"),
                    },
                )
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("structure_extraction: persistence failed")
            raise RuntimeError(str(exc)) from exc

    return {
        "warehouse_map_id": int(warehouse_map_id),
        "model_id": int(model_id),
        "client_flight_id": client_flight_id,
        "target_count": len(result.targets),
        "active_target_count": active_target_count,
        "review_target_count": review_target_count,
        "rejected_target_count": rejected_target_count,
        "coordinate_setup_status": "active" if active_target_count > 0 else "draft",
        "manual_review_required": quality_status != "ready" or review_target_count > 0,
        "rejected_clearance": result.rejected_clearance,
        "aisles": int(result.summary.get("counts", {}).get("aisles", 0)),
        "racks": int(result.summary.get("counts", {}).get("racks", 0)),
        "status": quality_status,
        "artifact_set_checksum": lineage_checksum,
        "layout_version_id": int(layout.id),
        "layout_published": published,
        "quality_status": quality_status,
        "quality_reasons": list(quality.get("reasons") or []),
        "confidence": quality.get("confidence"),
    }


async def extract_and_persist_structure(
    *,
    warehouse_map_id: int,
    model_id: int,
    client_flight_id: str,
    params: StructureExtractionParams | None = None,
) -> dict[str, Any]:
    """Run structure extraction for a flight and persist targets + asset."""
    record_extraction_running(warehouse_map_id=int(warehouse_map_id))
    effective = (params or StructureExtractionParams()).sanitized()
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
        readiness = await refresh_structure_input_readiness(timeout_s=8.0)
        live_occupancy = occupancy_grid_from_ros_yaml(readiness.occupancy_message)
        logger.info(
            "warehouse_structure_extract_readiness",
            extra={"warehouse_map_id": int(warehouse_map_id), **readiness.to_dict()},
        )
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
        _attach_quality_gate(result)
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
        record_extraction_failed(
            warehouse_map_id=int(warehouse_map_id),
            error_message=str(exc),
        )
        raise


def _attach_manifest_hints(result: StructureResult, client_flight_id: str) -> None:
    try:
        from backend.modules.warehouse.service.live_map_manifest import load_flight_manifest

        manifest = load_flight_manifest(client_flight_id)
    except Exception:
        logger.debug("structure_extraction_manifest_hints_failed", exc_info=True)
        return
    if manifest is None:
        return
    result.summary["map_quality"] = {
        "manifest_status": manifest.manifest_status,
        "map_quality": manifest.map_quality,
        "default_view_layer": manifest.default_view_layer,
        "rgbd_cloud_available": manifest.rgbd_cloud_available,
        "rgbd_has_rgb": manifest.rgbd_has_rgb,
        "diagnostic_nvblox_layers": list(manifest.diagnostic_nvblox_layers),
        "nvblox_available": bool(manifest.nvblox_available),
        "missing_topics": list(manifest.missing_topics or []),
        "chunk_counts": dict(manifest.chunk_counts or {}),
        "point_counts": dict(getattr(manifest, "point_counts", {}) or {}),
        "source_quality": dict(getattr(manifest, "source_quality", {}) or {}),
        "tf_degraded": bool(getattr(manifest, "tf_degraded", False)),
        "tf_jump_back_count": int(getattr(manifest, "tf_jump_back_count", 0) or 0),
        "tf_old_data_count": int(getattr(manifest, "tf_old_data_count", 0) or 0),
        "nvblox_restart_count": int(getattr(manifest, "nvblox_restart_count", 0) or 0),
    }
    clearance = result.summary.get("clearance")
    if isinstance(clearance, dict) and not manifest.nvblox_available:
        clearance.setdefault("source", "point_cloud_fallback")
        clearance.setdefault("missing_topics", list(manifest.missing_topics or []))


def _attach_quality_gate(result: StructureResult) -> None:
    """Mark suspicious auto-detect output as draft-only instead of trusted ready data."""
    ensure_structure_quality_summary(result.summary, rejected_clearance=result.rejected_clearance)


def ensure_structure_quality_summary(
    summary: dict[str, Any],
    *,
    rejected_clearance: int | None = None,
) -> dict[str, Any]:
    """Backfill quality metadata for new and legacy structure summaries."""
    existing = summary.get("quality") if isinstance(summary, dict) else None
    if isinstance(existing, dict) and existing.get("status"):
        return summary

    counts = summary.get("counts") if isinstance(summary, dict) else {}
    counts = counts if isinstance(counts, dict) else {}
    map_quality = summary.get("map_quality") if isinstance(summary, dict) else {}
    map_quality = map_quality if isinstance(map_quality, dict) else {}
    clearance = summary.get("clearance") if isinstance(summary, dict) else {}
    clearance = clearance if isinstance(clearance, dict) else {}

    candidate_count = int(counts.get("candidate_targets") or counts.get("targets") or 0)
    # New summaries carry an explicit active-target count produced by the
    # clearance classifier. Legacy summaries only have the total ``targets``
    # field (a candidate count), so the active tally is derived from the gate
    # status below instead of trusting that raw number.
    has_explicit_active_count = "active_targets" in counts
    target_count = int(
        counts.get("active_targets") if has_explicit_active_count else counts.get("targets") or 0
    )
    rack_count = int(counts.get("racks") or 0)
    aisle_count = int(counts.get("aisles") or 0)
    rejected = int(counts.get("rejected_clearance") or rejected_clearance or 0)
    if candidate_count <= 0:
        candidate_count = target_count + rejected
    rejection_ratio = float(rejected) / float(candidate_count) if candidate_count > 0 else 0.0
    targets_per_rack = (
        float(candidate_count) / float(rack_count) if rack_count > 0 else float(candidate_count)
    )
    chunk_counts = (
        map_quality.get("chunk_counts") if isinstance(map_quality.get("chunk_counts"), dict) else {}
    )
    point_counts = (
        map_quality.get("point_counts") if isinstance(map_quality.get("point_counts"), dict) else {}
    )
    source_quality = (
        map_quality.get("source_quality")
        if isinstance(map_quality.get("source_quality"), dict)
        else {}
    )
    clearance_source = str(clearance.get("source") or "unknown")

    reasons: list[str] = []
    if candidate_count <= 0 or rack_count <= 0 or aisle_count <= 0:
        reasons.append("insufficient_detected_structure")
    if rack_count > 0 and targets_per_rack > 24.0:
        reasons.append("too_many_targets_per_rack")
    if candidate_count >= 20 and rejection_ratio >= 0.40:
        reasons.append("clearance_rejection_ratio_high")
    diagnostics = summary.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    occupancy_available = (
        bool(diagnostics.get("occupancy_available"))
        or int(chunk_counts.get("nvblox_occupancy") or 0) > 0
    )
    esdf_available = (
        bool(diagnostics.get("esdf_available")) or int(chunk_counts.get("nvblox_esdf") or 0) > 0
    )
    if not occupancy_available:
        reasons.append("missing_occupancy_grid")
    if 0 < int(point_counts.get("nvblox_esdf") or 0) < 5_000:
        reasons.append("weak_esdf")
    esdf_quality = source_quality.get("nvblox_esdf") if isinstance(source_quality, dict) else None
    if isinstance(esdf_quality, dict):
        try:
            esdf_ppm2 = float(esdf_quality.get("points_per_m2") or 0.0)
        except (TypeError, ValueError):
            esdf_ppm2 = 0.0
        if 0.0 < esdf_ppm2 < 15.0:
            reasons.append("weak_esdf")
    if bool(map_quality.get("tf_degraded")) or int(map_quality.get("tf_jump_back_count") or 0) >= 3:
        reasons.append("tf_instability")
    missing_topics = map_quality.get("missing_topics")
    if not esdf_available and (
        not isinstance(missing_topics, list)
        or any("esdf" in str(topic) for topic in missing_topics)
    ):
        reasons.append("missing_esdf_topic")

    unique_reasons = sorted(set(reasons))
    confidence = 1.0
    if "missing_occupancy_grid" in unique_reasons:
        confidence -= 0.35
    if "clearance_rejection_ratio_high" in unique_reasons:
        confidence -= 0.25
    if "too_many_targets_per_rack" in unique_reasons:
        confidence -= 0.25
    if "weak_esdf" in unique_reasons:
        confidence -= 0.10
    if "tf_instability" in unique_reasons:
        confidence -= 0.20
    if "insufficient_detected_structure" in unique_reasons:
        confidence -= 0.50
    confidence = max(0.0, min(1.0, confidence))
    status = "needs_review" if unique_reasons else "ready"

    if has_explicit_active_count:
        active_target_count = target_count
    else:
        # Legacy summaries cannot distinguish active from candidate targets, so
        # only trust them as active when the gate is clean.
        active_target_count = target_count if status == "ready" else 0

    summary["quality"] = {
        "status": status,
        "confidence": round(confidence, 3),
        "reasons": unique_reasons,
        "target_count": target_count,
        "active_target_count": active_target_count,
        "candidate_count": candidate_count,
        "rejected_clearance": rejected,
        "rejection_ratio": round(rejection_ratio, 3),
        "targets_per_rack": round(targets_per_rack, 3) if rack_count > 0 else None,
        "clearance_source": clearance_source,
        "tf_degraded": bool(map_quality.get("tf_degraded")),
        "tf_jump_back_count": int(map_quality.get("tf_jump_back_count") or 0),
    }
    return summary


async def resolve_latest_model_flight(
    db,
    *,
    warehouse_map_id: int,
) -> tuple[int, str] | None:
    """Return (model_id, client_flight_id) for the newest ready model of a map.

    Reads the client_flight_id from the mapping job params persisted by
    ``persist_capture``. Returns ``None`` when nothing is extractable yet.
    """
    from backend.modules.warehouse.models import WarehouseMappingJob

    rows = (
        await db.execute(
            select(WarehouseMappingJob, WarehouseModel)
            .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
            .where(
                WarehouseMappingJob.warehouse_map_id == int(warehouse_map_id),
                WarehouseModel.status == "ready",
            )
            .order_by(WarehouseMappingJob.id.desc())
            .limit(10)
        )
    ).all()
    for job, model in rows:
        params = job.params if isinstance(job.params, dict) else {}
        capture = params.get("capture_result")
        capture = capture if isinstance(capture, dict) else {}
        flight = capture.get("client_flight_id") or params.get("client_flight_id")
        token = str(flight or "").strip()
        if token:
            return int(model.id), token
    return None
