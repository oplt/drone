"""Warehouse live-map bridge — start, stop, and status."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.core.config.runtime import env_truthy, settings

from . import state
from .publish_loop import _publish_loop

logger = logging.getLogger(__name__)


async def start_warehouse_live_map_bridge(flight_id: str) -> None:
    """Stream warehouse odometry + Nvblox ESDF pointcloud metadata into live voxel map."""
    if not env_truthy(settings.warehouse_live_map_publish):
        return

    async with state._bridge_lock:
        await _stop_warehouse_live_map_bridge_locked(stop_child_bridges=False)
        stop = asyncio.Event()
        state._bridge_stop = stop
        state._bridge_flight_id = flight_id
        state._bridge_task = asyncio.create_task(
            _publish_loop(flight_id, stop),
            name=f"warehouse-live-map-bridge:{flight_id}",
        )


async def _stop_child_bridges() -> None:
    child_stoppers = (
        (
            "raw point-cloud live map bridge",
            "backend.modules.warehouse.service.raw_pointcloud_live_map_bridge",
            "stop_raw_pointcloud_live_map_bridge",
        ),
        (
            "colored point-cloud live map bridge",
            "backend.modules.warehouse.service.colored_pointcloud_live_map_bridge",
            "stop_colored_pointcloud_live_map_bridge",
        ),
        (
            "nvblox layers live map bridge",
            "backend.modules.warehouse.service.nvblox_layers_live_map_bridge",
            "stop_nvblox_layers_live_map_bridge",
        ),
    )

    for label, module_name, function_name in child_stoppers:
        try:
            module = __import__(module_name, fromlist=[function_name])
            stopper = getattr(module, function_name)
            await stopper()
        except Exception:
            logger.exception("Failed to stop %s", label)


async def _stop_warehouse_live_map_bridge_locked(*, stop_child_bridges: bool = True) -> None:
    task = state._bridge_task
    stop = state._bridge_stop
    if stop is not None:
        stop.set()

    if task is not None:
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Warehouse live map bridge task stopped with an error")

    state._bridge_task = None
    state._bridge_flight_id = None
    state._bridge_stop = None

    if stop_child_bridges:
        await _stop_child_bridges()


async def stop_warehouse_live_map_bridge() -> None:
    async with state._bridge_lock:
        await _stop_warehouse_live_map_bridge_locked(stop_child_bridges=True)


def live_map_bridge_status() -> dict[str, Any]:
    running = state._bridge_task is not None and not state._bridge_task.done()
    return {
        "running": running,
        "flight_id": state._bridge_flight_id,
    }


__all__ = [
    "_stop_warehouse_live_map_bridge_locked",
    "live_map_bridge_status",
    "start_warehouse_live_map_bridge",
    "stop_warehouse_live_map_bridge",
]
