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
import threading
from collections.abc import Coroutine
from typing import Any

from celery.signals import worker_ready

from backend.core.config.runtime import settings, setup_logging
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.warehouse.service.structure_extraction import (
    StructureExtractionParams,
)
from backend.modules.warehouse.service.structure_jobs import (
    EXTRACTION_TASK_NAME,
    extract_and_persist_structure,
    record_extraction_failed,
)

logger = logging.getLogger(__name__)
setup_logging()

WAREHOUSE_MAPPING_QUEUE = settings.celery_warehouse_mapping_queue
_loop_lock = threading.Lock()
_thread_local_state = threading.local()
_TASK_NAME = EXTRACTION_TASK_NAME


@worker_ready.connect
def _verify_warehouse_mapping_tasks_registered(**_kwargs: Any) -> None:
    if _TASK_NAME not in celery_app.tasks:
        logger.error(
            "warehouse_mapping worker boot: task %s is NOT registered; "
            "auto-detect will discard extraction jobs until the worker restarts.",
            _TASK_NAME,
        )
        return
    logger.info("warehouse_mapping worker boot: registered task %s", _TASK_NAME)


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    loop = getattr(_thread_local_state, "loop", None)
    if loop is not None and not loop.is_closed():
        return loop
    with _loop_lock:
        loop = getattr(_thread_local_state, "loop", None)
        if loop is not None and not loop.is_closed():
            return loop
        loop = asyncio.new_event_loop()
        _thread_local_state.loop = loop
        return loop


def _run_on_worker_loop(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    loop = _get_worker_loop()
    if loop.is_running():
        raise RuntimeError("Warehouse mapping worker event loop is already running.")
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _params_from_payload(payload: dict[str, Any] | None) -> StructureExtractionParams:
    payload = payload or {}
    defaults = StructureExtractionParams(
        voxel_m=settings.warehouse_structure_voxel_m,
        grid_res_m=settings.warehouse_structure_grid_res_m,
        floor_margin_m=settings.warehouse_structure_floor_margin_m,
        ceiling_max_m=settings.warehouse_structure_ceiling_max_m,
        min_aisle_width_m=settings.warehouse_structure_min_aisle_width_m,
        min_rack_length_m=settings.warehouse_structure_min_rack_length_m,
        bin_pitch_m=settings.warehouse_structure_bin_pitch_m,
        shelf_min_spacing_m=settings.warehouse_structure_shelf_min_spacing_m,
        max_shelf_levels=settings.warehouse_structure_max_shelf_levels,
        max_bins_per_rack_face=settings.warehouse_structure_max_bins_per_rack_face,
        standoff_m=settings.warehouse_structure_standoff_m,
        drone_radius_m=settings.warehouse_structure_drone_radius_m,
        clearance_margin_m=settings.warehouse_structure_clearance_margin_m,
        max_points=settings.warehouse_structure_max_points,
    )

    def _override(name: str, current: float) -> float:
        value = payload.get(name)
        if value is None:
            return current
        try:
            return float(value)
        except (TypeError, ValueError):
            return current

    defaults.voxel_m = _override("voxel_m", defaults.voxel_m)
    defaults.grid_res_m = _override("grid_res_m", defaults.grid_res_m)
    defaults.bin_pitch_m = _override("bin_pitch_m", defaults.bin_pitch_m)
    defaults.standoff_m = _override("standoff_m", defaults.standoff_m)
    defaults.drone_radius_m = _override("drone_radius_m", defaults.drone_radius_m)
    defaults.clearance_margin_m = _override("clearance_margin_m", defaults.clearance_margin_m)
    defaults.min_aisle_width_m = _override("min_aisle_width_m", defaults.min_aisle_width_m)
    defaults.shelf_min_spacing_m = _override("shelf_min_spacing_m", defaults.shelf_min_spacing_m)
    defaults.max_shelf_levels = int(_override("max_shelf_levels", defaults.max_shelf_levels))
    defaults.max_bins_per_rack_face = int(
        _override("max_bins_per_rack_face", defaults.max_bins_per_rack_face)
    )
    axis = payload.get("axis_deg")
    defaults.axis_deg = None if axis is None else _override("axis_deg", 0.0)
    return defaults.sanitized()


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
                params=_params_from_payload(params),
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
            record_extraction_failed(
                warehouse_map_id=int(warehouse_map_id),
                error_message=str(exc),
            )
        raise self.retry(exc=exc, countdown=30) from exc
