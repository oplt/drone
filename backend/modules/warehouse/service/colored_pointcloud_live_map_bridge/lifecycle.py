"""Colored point-cloud live-map bridge — start, drain, and stop."""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from .constants import COLORED_BRIDGE_SOURCES
from .helpers import _note_mapping_startup
from .node import _ColoredPointCloudLiveMapNode
from .source_resolution import _runtime_busy, _sources_with_late_publisher_fallbacks
from . import state

logger = logging.getLogger(__name__)


async def start_colored_pointcloud_live_map_bridge(
    flight_id: str,
    *,
    source_ids: tuple[str, ...] = COLORED_BRIDGE_SOURCES,
) -> None:
    async with state._runtime_lock:
        await stop_colored_pointcloud_live_map_bridge()

        from backend.modules.warehouse.service.live_map_readiness import (
            probe_live_map_topic_types,
            resolve_colored_bridge_sources,
        )

        topic_probes_list, _ = await asyncio.to_thread(probe_live_map_topic_types)
        topic_probes = {probe.topic: probe for probe in topic_probes_list}

        resolved_sources = resolve_colored_bridge_sources(topic_probes=topic_probes)
        sources, missing_sources = _sources_with_late_publisher_fallbacks(
            resolved_sources,
            source_ids,
        )
        if missing_sources:
            logger.warning(
                "Requested colored live-map sources are not publishing yet; subscribing to "
                "their configured topics so late publishers are captured: %s",
                sorted(missing_sources),
            )
        if not sources:
            logger.warning("No valid colored live-map sources requested: %s", sorted(source_ids))
            return

        from backend.infrastructure.warehouse.bridge_config import (
            configure_embedded_ros_environment,
        )

        configure_embedded_ros_environment()
        import rclpy
        from rclpy.executors import SingleThreadedExecutor

        if not rclpy.ok():
            rclpy.init(args=None)

        loop = asyncio.get_running_loop()
        wrapper = _ColoredPointCloudLiveMapNode(
            flight_id=flight_id,
            event_loop=loop,
            sources=sources,
        )

        executor = SingleThreadedExecutor()
        executor.add_node(wrapper.node)

        thread = threading.Thread(
            target=executor.spin,
            name="warehouse-colored-pointcloud-live-map-bridge",
            daemon=True,
        )
        thread.start()

        state._runtime = state._ColoredBridgeRuntime(
            node=wrapper.node,
            executor=executor,
            thread=thread,
            sources=wrapper.source_runtimes,
        )

        _note_mapping_startup("bridge_start_monotonic")

        logger.info(
            "Started colored point-cloud live-map bridge flight_id=%s sources=%s",
            flight_id,
            list(sources.keys()),
        )


async def drain_colored_pointcloud_live_map_bridge(*, timeout_s: float = 5.0) -> bool:
    """Wait for in-flight colored point-cloud chunks to finish publishing."""
    runtime = state._runtime
    if runtime is None:
        return True

    deadline = time.monotonic() + max(0.1, timeout_s)
    while time.monotonic() < deadline:
        if not _runtime_busy(runtime):
            logger.info(
                "Colored point-cloud bridge drained sources=%s",
                list(runtime.sources.keys()),
            )
            return True
        await asyncio.sleep(0.05)

    logger.warning(
        "Colored point-cloud bridge drain timed out after %.1fs sources=%s",
        timeout_s,
        list(runtime.sources.keys()),
    )
    return False


async def stop_colored_pointcloud_live_map_bridge() -> None:
    runtime = state._runtime
    state._runtime = None

    if runtime is None:
        return

    try:
        await asyncio.to_thread(runtime.executor.shutdown)
    except Exception:
        logger.exception("Failed to shutdown colored point-cloud executor")

    try:
        runtime.node.destroy_node()
    except Exception:
        logger.exception("Failed to destroy colored point-cloud node")

    if runtime.thread.is_alive():
        await asyncio.to_thread(runtime.thread.join, 2.0)

    logger.info("Stopped colored point-cloud live-map bridge")


__all__ = [
    "drain_colored_pointcloud_live_map_bridge",
    "start_colored_pointcloud_live_map_bridge",
    "stop_colored_pointcloud_live_map_bridge",
]
