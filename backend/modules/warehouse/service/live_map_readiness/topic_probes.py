"""Warehouse live-map readiness — topic probes."""

from __future__ import annotations


import concurrent.futures
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

from backend.infrastructure.cache.redis import get_sync_redis_client
from backend.modules.warehouse.service.map_source_config import (
    NVBLOX_INTERNAL_LAYER_TOPICS,
    NVBLOX_OPTIONAL_ESDF_TOPICS,
    NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
    OCCUPANCY_TOPIC_CANDIDATES,
    RGBD_INPUT_TOPICS,
    WAREHOUSE_LIVE_MAP_SOURCES,
)

from .constants import _MAX_TOPIC_INFO_WORKERS

logger = logging.getLogger(__name__)
from . import cache as readiness_cache
from . import deps
from .constants import _TOPIC_PROBE_KEY
from .models import TopicTypeProbe
from .ros_commands import _ros2_workspace, _topic_info
from .topic_classification import classify_topic_for_bridge

def _probe_specs_for_topics(topics: set[str]) -> list[tuple[str, bool, bool, bool]]:
    probe_specs: list[tuple[str, bool, bool, bool]] = []
    for topic in RGBD_INPUT_TOPICS:
        probe_specs.append((topic, False, False, True))
    probe_specs.append((WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic, True, False, True))
    for topic in NVBLOX_INTERNAL_LAYER_TOPICS:
        probe_specs.append((topic, False, True, False))
    for topic in NVBLOX_REQUIRED_POINTCLOUD_TOPICS:
        probe_specs.append((topic, True, False, False))
    for topic in NVBLOX_OPTIONAL_ESDF_TOPICS:
        probe_specs.append((topic, True, False, False))
    for topic in OCCUPANCY_TOPIC_CANDIDATES:
        probe_specs.append((topic, False, False, False))
    for topic in sorted(topics):
        if topic.startswith("/nvblox_node/back_projected_depth/"):
            probe_specs.append((topic, True, False, False))

    seen: set[str] = set()
    deduped: list[tuple[str, bool, bool, bool]] = []
    for item in probe_specs:
        if item[0] in seen:
            continue
        seen.add(item[0])
        deduped.append(item)
    return deduped

def _collect_topic_types(topics_to_probe: list[str], *, topics: set[str], ws: Path) -> dict[str, str | None]:
    present_topics = [topic for topic in topics_to_probe if topic in topics]
    if not present_topics:
        return {}
    max_workers = min(_MAX_TOPIC_INFO_WORKERS, len(present_topics))
    topic_types: dict[str, str | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ros-topic-info") as pool:
        future_by_topic = {
            pool.submit(deps.resolve("_topic_info"), topic, ws): topic for topic in present_topics
        }
        for future in concurrent.futures.as_completed(future_by_topic):
            topic = future_by_topic[future]
            try:
                topic_types[topic] = future.result()
            except Exception:
                topic_types[topic] = None
    return topic_types

def probe_live_map_topic_types(
    *,
    topics: set[str] | None = None,
    quiet: bool = False,
    use_cache: bool = True,
) -> tuple[list[TopicTypeProbe], dict[str, str | None]]:
    ttl = readiness_cache._topic_probe_cache_ttl_s()
    if (
        use_cache
        and ttl > 0.0
        and readiness_cache._topic_probe_cache is not None
        and topics is None
    ):
        if (time.monotonic() - readiness_cache._topic_probe_cache_at) < ttl:
            return readiness_cache._topic_probe_cache
    if use_cache and ttl > 0.0 and topics is None:
        try:
            payload = get_sync_redis_client().get(_TOPIC_PROBE_KEY)
            if payload:
                raw = json.loads(payload)
                result = (
                    [TopicTypeProbe(**item) for item in raw.get("probes") or []],
                    dict(raw.get("topic_types") or {}),
                )
                readiness_cache._topic_probe_cache = result
                readiness_cache._topic_probe_cache_at = time.monotonic()
                return result
        except Exception:
            logger.debug("topic_probe_shared_state_read_failed", exc_info=True)

    ws = _ros2_workspace()
    if topics is None:
        try:
            topics = set(deps.resolve("list_ros2_topics")(ws))
        except RuntimeError as exc:
            logger.warning("Could not list ROS topics for type probe: %s", exc)
            topics = set()

    probe_specs = _probe_specs_for_topics(topics)
    topic_types = _collect_topic_types([spec[0] for spec in probe_specs], topics=topics, ws=ws)
    probes: list[TopicTypeProbe] = []
    rgb_inputs_present = all(topic in topics for topic in RGBD_INPUT_TOPICS)

    for topic, expect_pc2, internal_layer, required in probe_specs:
        present = topic in topics
        msg_type = topic_types.get(topic) if present else None
        probe = classify_topic_for_bridge(
            topic=topic,
            present=present,
            message_type=msg_type,
            expect_pointcloud2=expect_pc2,
            internal_layer=internal_layer,
        )
        if topic == WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic and not present and rgb_inputs_present:
            probe = TopicTypeProbe(
                topic=topic,
                present=False,
                bridge_kind="missing",
                info=(
                    f"{topic} is not bridged; nvblox will map from RGB-D "
                    "depth/color/camera_info instead"
                ),
            )
        probes.append(probe)
        if quiet:
            continue
        if probe.warning and required:
            logger.warning("Live-map topic probe: %s", probe.warning)
        elif probe.warning and not required:
            logger.debug("Live-map optional topic probe: %s", probe.warning)
        elif probe.info:
            logger.info("Live-map topic probe: %s", probe.info)

    result = (probes, topic_types)
    if use_cache and topics is None:
        readiness_cache._topic_probe_cache = result
        readiness_cache._topic_probe_cache_at = time.monotonic()
        try:
            get_sync_redis_client().setex(
                _TOPIC_PROBE_KEY,
                max(1, int(ttl)),
                json.dumps(
                    {
                        "probes": [asdict(probe) for probe in probes],
                        "topic_types": topic_types,
                    },
                    separators=(",", ":"),
                ),
            )
        except Exception:
            logger.debug("topic_probe_shared_state_unavailable", exc_info=True)
    return result

def probe_nvblox_topic_types() -> list[TopicTypeProbe]:
    probes, _ = probe_live_map_topic_types()
    return probes
