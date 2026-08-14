"""Warehouse live-map readiness — bridge sources."""

from __future__ import annotations


import logging
from dataclasses import replace

from backend.modules.warehouse.service.map_source_config import (
    WAREHOUSE_LIVE_MAP_SOURCES,
    LiveMapSourceConfig,
)

logger = logging.getLogger(__name__)
from . import deps
from .models import TopicTypeProbe
from .ros_commands import _ros2_workspace
from .topic_classification import discover_nvblox_pointcloud_topics, discover_rgbd_pointcloud_topics

def resolve_colored_bridge_sources(
    *,
    topic_probes: dict[str, TopicTypeProbe] | None = None,
    topics: set[str] | None = None,
    rgbd_pointcloud_topic: str | None = None,
) -> dict[str, LiveMapSourceConfig]:
    if topics is None:
        ws = _ros2_workspace()
        try:
            topics = set(deps.resolve("list_ros2_topics")(ws))
        except RuntimeError:
            topics = set()

    if topic_probes:
        topic_types = {
            topic: probe.message_type
            for topic, probe in topic_probes.items()
            if probe.message_type is not None
        }
    else:
        _, topic_types = deps.resolve("probe_live_map_topic_types")(topics=topics, quiet=True)

    rgbd_candidates = discover_rgbd_pointcloud_topics(topics, topic_types=topic_types)
    resolved_rgbd = rgbd_pointcloud_topic or (rgbd_candidates[0] if rgbd_candidates else None)

    sources: dict[str, LiveMapSourceConfig] = {}

    if resolved_rgbd:
        base = WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"]
        sources["rgbd_colored"] = replace(base, topic=resolved_rgbd)
    else:
        logger.warning(
            "No PointCloud2 RGB-D topic found; rgbd_colored live-map source disabled. "
            "Ensure /warehouse/front/rgbd/points is bridged or nvblox back_projected_depth "
            "is publishing after camera integration."
        )

    nvblox_pc_topics = discover_nvblox_pointcloud_topics(topics, topic_types=topic_types)
    back_projected_topic: str | None = None
    for topic in nvblox_pc_topics:
        if topic.endswith("static_esdf_pointcloud"):
            sources.setdefault(
                "nvblox_esdf",
                replace(WAREHOUSE_LIVE_MAP_SOURCES["nvblox_esdf"], topic=topic),
            )
        elif topic.startswith("/nvblox_node/back_projected_depth/"):
            back_projected_topic = topic

    if back_projected_topic and "rgbd_colored" not in sources:
        sources["rgbd_colored"] = replace(
            WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"],
            topic=back_projected_topic,
            source_id="rgbd_colored",
            layer="rgbd_colored",
        )

    if topic_probes:
        for source_id in list(sources):
            config = sources[source_id]
            probe = topic_probes.get(config.topic)
            if probe is not None and probe.present and not probe.ok_for_pointcloud_bridge:
                logger.warning(
                    "Removing colored live-map source=%s topic=%s: %s",
                    source_id,
                    config.topic,
                    probe.warning or probe.info,
                )
                sources.pop(source_id, None)

    return sources
