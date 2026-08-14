"""Warehouse live-map readiness — rgbd wait."""

from __future__ import annotations


import asyncio
import logging
import time
from pathlib import Path

from backend.modules.warehouse.service.map_source_config import RGBD_VISUALIZATION_TOPIC

logger = logging.getLogger(__name__)
from .constants import _MAX_MESSAGE_PROBE_CONCURRENCY
from . import deps
from .cache import _store_rgbd_readiness_cache
from .models import MappingReadinessResult, TopicTypeProbe
from .ros_commands import _ros2_workspace, _topic_has_message
from .startup_timing import _active_mapping_startup_timing, _note_mapping_startup
from .topic_classification import (
    _rgbd_visualization_probe_topics,
    discover_nvblox_pointcloud_topics,
    discover_rgbd_pointcloud_topics,
)
from .rgb_inputs import _rgb_inputs_ready

async def _probe_messages(
    *,
    topics: list[str],
    ws: Path,
    per_topic_timeout_s: float,
) -> set[str]:
    semaphore = asyncio.Semaphore(_MAX_MESSAGE_PROBE_CONCURRENCY)

    async def _one(topic: str) -> tuple[str, bool]:
        async with semaphore:
            return topic, await deps.asyncio.to_thread(
                _topic_has_message, topic, ws, timeout_s=per_topic_timeout_s
            )

    publishing: set[str] = set()
    for topic, ok in await asyncio.gather(*[_one(topic) for topic in topics]):
        if ok:
            publishing.add(topic)
    return publishing

def _timing_ms(wait_started: float) -> dict[str, int]:
    timing = {"wait_for_rgbd_mapping_topics_ms": int((time.monotonic() - wait_started) * 1000)}
    active = _active_mapping_startup_timing()
    if active is not None:
        try:
            timing.update(active.as_dict())
        except Exception:
            logger.debug("Could not merge active mapping startup timing", exc_info=True)
    return timing

async def wait_for_rgbd_mapping_topics(
    *,
    timeout_s: float,
    poll_s: float = 0.5,
) -> MappingReadinessResult:
    ws = _ros2_workspace()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, timeout_s)
    wait_started = time.monotonic()
    last_probes: list[TopicTypeProbe] = []
    last_warnings: list[str] = []
    rgbd_pointcloud_topic: str | None = None
    first_rgbd_msg_at: float | None = None

    while loop.time() < deadline:
        try:
            topics = await deps.list_topics_async(ws)
        except RuntimeError:
            topics = set()

        rgbd_candidates = discover_rgbd_pointcloud_topics(topics)
        probe_topics = [topic for topic in _rgbd_visualization_probe_topics(topics) if topic in topics]
        remaining = max(0.2, deadline - loop.time())
        per_topic_timeout = min(3.0, max(0.5, remaining / max(1, min(len(probe_topics), _MAX_MESSAGE_PROBE_CONCURRENCY))))
        publishing = await _probe_messages(topics=probe_topics, ws=ws, per_topic_timeout_s=per_topic_timeout)

        if first_rgbd_msg_at is None:
            first_msg_topic = next((topic for topic in rgbd_candidates if topic in publishing), None)
            if first_msg_topic is not None:
                first_rgbd_msg_at = time.monotonic()
                _note_mapping_startup("first_rgbd_pointcloud_msg_monotonic")

        rgbd_pointcloud_topic = next(
            (topic for topic in rgbd_candidates if topic in publishing),
            rgbd_candidates[0] if rgbd_candidates else None,
        )
        rgbd_pc_ready = bool(rgbd_pointcloud_topic and rgbd_pointcloud_topic in publishing)
        rgb_inputs_ready, missing_inputs = _rgb_inputs_ready(topics, publishing)

        if rgbd_pc_ready:
            _note_mapping_startup("rgbd_readiness_monotonic")
            last_probes, topic_types = deps.resolve("probe_live_map_topic_types")(
                topics=topics, quiet=True
            )
            last_warnings = [p.warning for p in last_probes if p.warning and p.topic in probe_topics]
            nvblox_pc_topics = discover_nvblox_pointcloud_topics(topics, topic_types=topic_types)
            result = MappingReadinessResult(
                ready=True,
                missing_topics=[],
                topic_probes=last_probes,
                warnings=last_warnings,
                rgbd_pointcloud_topic=rgbd_pointcloud_topic,
                rgbd_input_topics_ready=rgb_inputs_ready,
                nvblox_pointcloud_topics=nvblox_pc_topics,
                timing_ms=_timing_ms(wait_started),
            )
            _store_rgbd_readiness_cache(result)
            return result

        if rgb_inputs_ready and RGBD_VISUALIZATION_TOPIC not in topics:
            _note_mapping_startup("rgbd_readiness_monotonic")
            last_probes, topic_types = deps.resolve("probe_live_map_topic_types")(
                topics=topics, quiet=True
            )
            nvblox_pc_topics = discover_nvblox_pointcloud_topics(topics, topic_types=topic_types)
            result = MappingReadinessResult(
                ready=True,
                missing_topics=missing_inputs,
                topic_probes=last_probes,
                warnings=last_warnings,
                rgbd_pointcloud_topic=rgbd_pointcloud_topic,
                rgbd_input_topics_ready=True,
                nvblox_pointcloud_topics=nvblox_pc_topics,
                timing_ms=_timing_ms(wait_started),
            )
            _store_rgbd_readiness_cache(result)
            return result

        await asyncio.sleep(min(max(0.15, poll_s), max(0.15, deadline - loop.time())))

    try:
        topics = await deps.list_topics_async(ws)
    except RuntimeError:
        topics = set()
    last_probes, topic_types = await deps.asyncio.to_thread(
        deps.resolve("probe_live_map_topic_types"), topics=topics
    )
    _, missing_inputs = _rgb_inputs_ready(topics, set())
    rgbd_candidates = discover_rgbd_pointcloud_topics(topics, topic_types=topic_types)
    return MappingReadinessResult(
        ready=False,
        missing_topics=missing_inputs,
        topic_probes=last_probes,
        warnings=[
            *last_warnings,
            "Timed out waiting for RGB-D PointCloud2 visualization stream "
            f"(expected one of: {', '.join(_rgbd_visualization_probe_topics(topics))})",
        ],
        rgbd_pointcloud_topic=rgbd_candidates[0] if rgbd_candidates else None,
        rgbd_input_topics_ready=False,
        nvblox_pointcloud_topics=discover_nvblox_pointcloud_topics(topics, topic_types=topic_types),
        timing_ms=_timing_ms(wait_started),
    )
