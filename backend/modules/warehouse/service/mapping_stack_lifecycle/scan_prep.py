"""Warehouse mapping stack lifecycle — scan ROS preparation."""

from __future__ import annotations

import asyncio
import logging

from backend.modules.warehouse.service.readiness_result import (
    WarehouseReadinessResult,
    readiness_for_takeoff,
    readiness_from_perception_status_strict,
)

from .helpers import (
    _is_mapping_stack_process_running,
    _mapping_stack_pid,
    _merge_nvblox_readiness_from_rgbd,
    _stack_status_field,
)
from .models import WarehouseMappingStackStatus
from .start import _maybe_start_mapping_stack_cmd

logger = logging.getLogger(__name__)


async def prepare_warehouse_scan_ros(
    *,
    require_nvblox: bool,
    sensor_timeout_s: float,
    nvblox_timeout_s: float,
    wait_for_rgbd: bool = True,
) -> tuple[
    WarehouseMappingStackStatus,
    WarehouseReadinessResult,
    WarehouseReadinessResult,
    "MappingReadinessResult",
]:
    from backend.modules.warehouse.service.live_map_readiness import (
        MappingReadinessResult,
        peek_cached_rgbd_readiness,
        wait_for_rgbd_mapping_topics,
    )
    from backend.modules.warehouse.service.warehouse_preflight import (
        fetch_warehouse_perception_status,
    )

    await _maybe_start_mapping_stack_cmd()

    status = await fetch_warehouse_perception_status(deep=True, force=True)
    takeoff_ready = readiness_for_takeoff(status)
    flight_readiness = readiness_from_perception_status_strict(status)

    if wait_for_rgbd and sensor_timeout_s > 0:
        cached_rgbd = peek_cached_rgbd_readiness()
        if cached_rgbd is not None and cached_rgbd.ready:
            rgbd_readiness = cached_rgbd
            logger.info(
                "Reusing pre-warmed RGB-D readiness (topic=%r nvblox_pointclouds=%s)",
                rgbd_readiness.rgbd_pointcloud_topic,
                rgbd_readiness.nvblox_pointcloud_topics,
            )
        else:
            rgbd_readiness = await wait_for_rgbd_mapping_topics(timeout_s=sensor_timeout_s)
        if not rgbd_readiness.ready:
            logger.warning(
                "RGB-D mapping topics not fully ready after %.1fs; missing=%s warnings=%s",
                sensor_timeout_s,
                rgbd_readiness.missing_topics,
                rgbd_readiness.warnings,
            )
        else:
            flags = rgbd_readiness.readiness_flags()
            if flags["rgbd_colored_pointcloud_ready"]:
                logger.info(
                    "RGB-D PointCloud2 stream ready for warehouse scan "
                    "(topic=%r nvblox_pointclouds=%s)",
                    rgbd_readiness.rgbd_pointcloud_topic,
                    rgbd_readiness.nvblox_pointcloud_topics,
                )
            elif flags["rgbd_input_ready"]:
                logger.info(
                    "RGB-D camera inputs ready for nvblox integration "
                    "(inputs_ready=%s nvblox_pointclouds=%s)",
                    rgbd_readiness.rgbd_input_topics_ready,
                    rgbd_readiness.nvblox_pointcloud_topics,
                )
            else:
                logger.info(
                    "RGB-D mapping readiness satisfied with partial inputs (%s)",
                    rgbd_readiness.to_dict(),
                )
    else:
        rgbd_readiness = MappingReadinessResult(
            ready=False,
            warnings=["RGB-D warmup deferred until after takeoff"],
        )
        logger.info(
            "Skipping RGB-D readiness wait before takeoff (wait_for_rgbd=%s timeout=%.1fs)",
            wait_for_rgbd,
            sensor_timeout_s,
        )

    deadline = asyncio.get_running_loop().time() + max(0.0, nvblox_timeout_s)
    flight_readiness = _merge_nvblox_readiness_from_rgbd(flight_readiness, rgbd_readiness)

    while require_nvblox and not flight_readiness.nvblox_ready:
        if asyncio.get_running_loop().time() >= deadline:
            flight_readiness = WarehouseReadinessResult(
                **{
                    **flight_readiness.to_dict(),
                    "ready": False,
                    "detail": flight_readiness.detail
                    or "Nvblox is not publishing a ready ESDF/costmap signal.",
                }
            )
            break

        await asyncio.sleep(1.0)

        status = await fetch_warehouse_perception_status(
            deep=True, force=True, bypass_cache=True
        )
        takeoff_ready = readiness_for_takeoff(status)
        flight_readiness = readiness_from_perception_status_strict(status)
        flight_readiness = _merge_nvblox_readiness_from_rgbd(flight_readiness, rgbd_readiness)

    process_running = _is_mapping_stack_process_running()

    running = bool(
        process_running
        or status.reachable
        or status.configured
        or takeoff_ready.core_ready
    )

    if flight_readiness.nvblox_ready:
        phase = "ready"
    elif running:
        phase = "starting"
    else:
        phase = "stopped"

    stack_status = WarehouseMappingStackStatus(
        running=running,
        pid=_mapping_stack_pid(),
        started_at=_stack_status_field("_mapping_stack_started_at"),
        last_exit_code=_stack_status_field("_mapping_stack_last_exit_code"),
        last_error=None if takeoff_ready.core_ready else (
            takeoff_ready.detail or _stack_status_field("_mapping_stack_last_error")
        ),
        nvblox_running=flight_readiness.nvblox_ready,
        phase=phase,
    )

    return stack_status, flight_readiness, takeoff_ready, rgbd_readiness


__all__ = ["prepare_warehouse_scan_ros"]
