"""Raw point-cloud live-map bridge — start, drain, and stop."""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from backend.modules.warehouse.service.live_map_config import (
    raw_lidar_max_points,
    raw_lidar_min_publish_interval_s,
    raw_lidar_voxel_size_m,
    should_persist_raw_lidar_chunks,
)

from .constants import (
    DEFAULT_GLOBAL_FRAME,
    DEFAULT_MAX_POINTS,
    DEFAULT_MIN_PUBLISH_INTERVAL_S,
    DEFAULT_POINTCLOUD_TOPIC,
)
from .node import _RawPointCloudLiveMapNode
from . import state

logger = logging.getLogger(__name__)


async def start_raw_pointcloud_live_map_bridge(
    flight_id: str,
    *,
    topic: str = DEFAULT_POINTCLOUD_TOPIC,
    global_frame: str = DEFAULT_GLOBAL_FRAME,
    max_points: int = DEFAULT_MAX_POINTS,
    min_publish_interval_s: float = DEFAULT_MIN_PUBLISH_INTERVAL_S,
    persist_to_disk: bool | None = None,
) -> None:
    async with state._runtime_lock:
        await stop_raw_pointcloud_live_map_bridge()

        resolved_persist = (
            should_persist_raw_lidar_chunks() if persist_to_disk is None else bool(persist_to_disk)
        )
        resolved_max_points = (
            max_points if max_points != DEFAULT_MAX_POINTS else raw_lidar_max_points()
        )
        resolved_interval = (
            min_publish_interval_s
            if min_publish_interval_s != DEFAULT_MIN_PUBLISH_INTERVAL_S
            else raw_lidar_min_publish_interval_s()
        )
        resolved_voxel = raw_lidar_voxel_size_m()

        from backend.infrastructure.warehouse.bridge_config import (
            configure_embedded_ros_environment,
        )

        configure_embedded_ros_environment()
        import rclpy
        from rclpy.executors import SingleThreadedExecutor

        if not rclpy.ok():
            rclpy.init(args=None)

        loop = asyncio.get_running_loop()
        wrapper = _RawPointCloudLiveMapNode(
            flight_id=flight_id,
            event_loop=loop,
            topic=topic,
            global_frame=global_frame,
            max_points=resolved_max_points,
            min_publish_interval_s=resolved_interval,
            persist_to_disk=resolved_persist,
            voxel_size_m=resolved_voxel,
        )

        executor = SingleThreadedExecutor()
        executor.add_node(wrapper.node)
        thread = threading.Thread(
            target=executor.spin,
            name="warehouse-raw-pointcloud-live-map-bridge",
            daemon=True,
        )
        thread.start()

        state._runtime = state._RawPointCloudRuntime(
            node=wrapper.node,
            executor=executor,
            thread=thread,
            wrapper=wrapper,
        )

        logger.info(
            "Started raw point-cloud live-map bridge flight_id=%s topic=%s max_hz=%.2f "
            "voxel_size=%.3f max_points=%s persist=%s",
            flight_id,
            topic,
            1.0 / max(0.001, float(resolved_interval)),
            resolved_voxel,
            resolved_max_points,
            resolved_persist,
        )


async def drain_raw_pointcloud_live_map_bridge(*, timeout_s: float = 5.0) -> bool:
    runtime = state._runtime
    if runtime is None:
        return True
    wrapper = runtime.wrapper
    deadline = time.monotonic() + max(0.1, float(timeout_s))
    while time.monotonic() < deadline:
        with wrapper._state_lock:
            busy = wrapper._processing or wrapper._queued_msg is not None
        if not busy:
            return True
        await asyncio.sleep(0.05)
    logger.warning("Raw point-cloud bridge drain timed out after %.1fs", timeout_s)
    return False


async def stop_raw_pointcloud_live_map_bridge() -> None:
    runtime = state._runtime
    state._runtime = None
    if runtime is None:
        return

    try:
        await asyncio.to_thread(runtime.executor.shutdown)
    except Exception:
        logger.exception("Failed to shutdown raw point-cloud executor")

    try:
        await asyncio.to_thread(runtime.node.destroy_node)
    except Exception:
        logger.exception("Failed to destroy raw point-cloud node")

    if runtime.thread.is_alive():
        await asyncio.to_thread(runtime.thread.join, 2.0)

    logger.info("Stopped raw point-cloud live-map bridge")


__all__ = [
    "drain_raw_pointcloud_live_map_bridge",
    "start_raw_pointcloud_live_map_bridge",
    "stop_raw_pointcloud_live_map_bridge",
]
