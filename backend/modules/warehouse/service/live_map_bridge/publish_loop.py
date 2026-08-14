"""Warehouse live-map bridge — odometry and health publish loop."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from backend.infrastructure.warehouse.bridge_config import bridge_config_path
from backend.modules.warehouse.service.live_map_stream import (
    WarehouseLiveHealthFlags,
    WarehouseLivePose,
    normalize_live_map_payload,
    warehouse_live_map_stream,
)
from backend.modules.warehouse.service.map_source_config import WAREHOUSE_LIVE_MAP_SOURCES
from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker

from .nvblox_readiness import _esdf_topic, _nvblox_ready_from_topics
from .odometry import _odometry_topic, _read_odometry_pose
from .pointcloud_cli import _read_nvblox_chunk
from .ros_commands import _list_ros2_topics_safe
from .settings_helpers import _setting_bool, _setting_float
from .workspace import _ros2_workspace

logger = logging.getLogger(__name__)


async def _publish_loop(flight_id: str, stop: asyncio.Event) -> None:
    ws = _ros2_workspace()
    odom_topic = _odometry_topic()
    esdf_topic = _esdf_topic()
    poll_s = _setting_float("warehouse_live_map_poll_s", 1.0, minimum=0.2)
    cli_pointcloud_enabled = _setting_bool("warehouse_live_map_cli_pointcloud_enabled", False)
    cli_pointcloud_poll_s = _setting_float(
        "warehouse_live_map_cli_pointcloud_poll_s",
        max(2.0, poll_s * 5.0),
        minimum=1.0,
    )
    next_chunk_at = 0.0
    chunk_sequence = 0

    logger.info(
        "Warehouse live map bridge started flight_id=%s odom=%s esdf=%s config=%s cli_pointcloud=%s",
        flight_id,
        odom_topic,
        esdf_topic,
        bridge_config_path(ws),
        cli_pointcloud_enabled,
    )

    try:
        while not stop.is_set():
            try:
                pose_result, topics_result = await asyncio.gather(
                    asyncio.to_thread(_read_odometry_pose, topic=odom_topic, ws=ws),
                    asyncio.to_thread(_list_ros2_topics_safe, ws),
                )
                pose = pose_result if isinstance(pose_result, WarehouseLivePose) else None
                topics = topics_result if isinstance(topics_result, set) else set()
                nvblox_ok = _nvblox_ready_from_topics(topics=topics, esdf_topic=esdf_topic)
                nvblox_status = nvblox_status_tracker.status()

                rgbd_topic = WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic
                lidar_topic = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].topic
                changed_chunks: list[dict[str, Any]] = []

                now = time.monotonic()
                if cli_pointcloud_enabled and nvblox_ok and now >= next_chunk_at:
                    next_chunk_at = now + cli_pointcloud_poll_s
                    chunk_sequence += 1
                    chunk = await asyncio.to_thread(
                        _read_nvblox_chunk,
                        flight_id=flight_id,
                        topic=esdf_topic,
                        ws=ws,
                        sequence=chunk_sequence,
                    )
                    if chunk is not None:
                        changed_chunks.append(chunk)

                if pose is not None or changed_chunks:
                    health = WarehouseLiveHealthFlags(
                        nvblox_ready=nvblox_ok or nvblox_status == "live",
                        nvblox_status=nvblox_status,
                        rgbd_live=rgbd_topic in topics,
                        lidar_live=lidar_topic in topics,
                        mapping_recording=True,
                        stack_running=bool(topics),
                        missing_mesh=nvblox_status not in {"live", "degraded", "warming"},
                        missing_point_cloud=not (nvblox_ok or changed_chunks),
                    )

                    pose_payload = pose.model_dump(mode="python") if pose is not None else None
                    payload: dict[str, Any] = {
                        "flight_id": flight_id,
                        "timestamp": datetime.now(UTC),
                        "health": health.model_dump(mode="python"),
                        "changed_chunks": changed_chunks,
                    }
                    frames = {
                        str(chunk.get("frame_id") or "").strip()
                        for chunk in changed_chunks
                        if isinstance(chunk, dict)
                    }
                    if pose is not None:
                        frames.add(pose.frame_id)
                    frames.discard("")
                    if len(frames) != 1:
                        raise ValueError(
                            f"Live-map bridge produced missing or mixed frames: {sorted(frames)}"
                        )
                    payload["frame_id"] = frames.pop()
                    if pose_payload is not None:
                        payload["pose"] = pose_payload
                        payload["scan_path_sample"] = [pose_payload]

                    update = normalize_live_map_payload(payload)
                    await warehouse_live_map_stream.publish(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Warehouse live map bridge publish iteration failed")

            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_s)
            except TimeoutError:
                continue
    finally:
        logger.info("Warehouse live map bridge stopped flight_id=%s", flight_id)


__all__ = ["_publish_loop"]
