from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass, field, replace
from typing import Literal

from backend.infrastructure.warehouse.bridge_config import list_ros2_topics, ros_command_env
from backend.modules.warehouse.service.map_source_config import (
    NVBLOX_INTERNAL_LAYER_TOPICS,
    NVBLOX_OPTIONAL_ESDF_TOPICS,
    NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
    ODOM_PREFLIGHT_TOPICS,
    RGBD_INPUT_TOPICS,
    RGBD_POINTCLOUD_CANDIDATE_PREFIXES,
    RGBD_VISUALIZATION_TOPIC,
    WAREHOUSE_LIVE_MAP_SOURCES,
    LiveMapSourceConfig,
)

logger = logging.getLogger(__name__)

TopicBridgeKind = Literal[
    "pointcloud2",
    "internal_layer",
    "missing",
    "wrong_type",
]


@dataclass
class TopicTypeProbe:
    topic: str
    present: bool
    message_type: str | None = None
    bridge_kind: TopicBridgeKind = "missing"
    ok_for_pointcloud_bridge: bool = False
    warning: str | None = None
    info: str | None = None


@dataclass
class MappingReadinessResult:
    ready: bool
    missing_topics: list[str] = field(default_factory=list)
    topic_probes: list[TopicTypeProbe] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rgbd_pointcloud_topic: str | None = None
    rgbd_input_topics_ready: bool = False
    nvblox_pointcloud_topics: list[str] = field(default_factory=list)
    timing_ms: dict[str, int] = field(default_factory=dict)

    def readiness_flags(self) -> dict[str, bool]:
        probes_by_topic = {probe.topic: probe for probe in self.topic_probes}
        rgbd_pc_probe = (
            probes_by_topic.get(self.rgbd_pointcloud_topic)
            if self.rgbd_pointcloud_topic
            else None
        )
        return {
            "rgbd_input_ready": self.rgbd_input_topics_ready,
            "rgbd_colored_pointcloud_ready": bool(
                rgbd_pc_probe is not None and rgbd_pc_probe.ok_for_pointcloud_bridge
            ),
            "nvblox_esdf_ready": any(
                probe.topic.endswith("static_esdf_pointcloud")
                and probe.ok_for_pointcloud_bridge
                for probe in self.topic_probes
            ),
            "nvblox_color_layer_present": any(
                probe.topic.endswith("color_layer") and probe.present
                for probe in self.topic_probes
            ),
            "nvblox_tsdf_layer_present": any(
                probe.topic.endswith("tsdf_layer") and probe.present
                for probe in self.topic_probes
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "missing_topics": list(self.missing_topics),
            "warnings": list(self.warnings),
            "rgbd_pointcloud_topic": self.rgbd_pointcloud_topic,
            "rgbd_input_topics_ready": self.rgbd_input_topics_ready,
            "nvblox_pointcloud_topics": list(self.nvblox_pointcloud_topics),
            "readiness_flags": self.readiness_flags(),
            "timing_ms": dict(self.timing_ms),
        }


def _note_mapping_startup(mark: str) -> None:
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            note_mapping_startup,
        )

        note_mapping_startup(mark)
    except ModuleNotFoundError as exc:
        logger.warning("Optional mapping startup timing unavailable: %s", exc)


def _active_mapping_startup_timing():
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            active_mapping_startup_timing,
        )

        return active_mapping_startup_timing()
    except ModuleNotFoundError:
        return None


def _is_pointcloud2_type(message_type: str | None) -> bool:
    return bool(message_type and "sensor_msgs/msg/PointCloud2" in message_type)


def _is_voxel_block_layer_type(message_type: str | None) -> bool:
    return bool(message_type and "nvblox_msgs/msg/VoxelBlockLayer" in message_type)


def classify_topic_for_bridge(
    *,
    topic: str,
    present: bool,
    message_type: str | None,
    expect_pointcloud2: bool,
    internal_layer: bool = False,
) -> TopicTypeProbe:
    if not present:
        return TopicTypeProbe(
            topic=topic,
            present=False,
            bridge_kind="missing",
            warning=f"{topic} is missing from ROS graph",
        )

    if internal_layer and _is_voxel_block_layer_type(message_type):
        return TopicTypeProbe(
            topic=topic,
            present=True,
            message_type=message_type,
            bridge_kind="internal_layer",
            ok_for_pointcloud_bridge=False,
            info=(
                f"{topic} publishes internal nvblox layer blocks "
                f"({message_type}); use PointCloud2 export topics instead"
            ),
        )

    if expect_pointcloud2 and _is_pointcloud2_type(message_type):
        return TopicTypeProbe(
            topic=topic,
            present=True,
            message_type=message_type,
            bridge_kind="pointcloud2",
            ok_for_pointcloud_bridge=True,
        )

    if expect_pointcloud2:
        return TopicTypeProbe(
            topic=topic,
            present=True,
            message_type=message_type,
            bridge_kind="wrong_type",
            warning=(
                f"{topic} exists but type is {message_type!r}, "
                "expected sensor_msgs/msg/PointCloud2"
            ),
        )

    return TopicTypeProbe(
        topic=topic,
        present=True,
        message_type=message_type,
        bridge_kind="pointcloud2" if _is_pointcloud2_type(message_type) else "wrong_type",
        ok_for_pointcloud_bridge=_is_pointcloud2_type(message_type),
    )


def discover_rgbd_pointcloud_topics(
    topics: set[str],
    *,
    topic_types: dict[str, str | None] | None = None,
) -> list[str]:
    """Return PointCloud2 RGB-D sources, preferring the warehouse bridge topic."""
    ordered: list[str] = []
    primary = WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic
    if primary in topics:
        msg_type = (topic_types or {}).get(primary)
        if msg_type is None or _is_pointcloud2_type(msg_type):
            ordered.append(primary)

    for prefix in RGBD_POINTCLOUD_CANDIDATE_PREFIXES:
        for topic in sorted(topics):
            if not topic.startswith(prefix):
                continue
            msg_type = (topic_types or {}).get(topic)
            if msg_type is not None and not _is_pointcloud2_type(msg_type):
                continue
            if topic not in ordered:
                ordered.append(topic)
    return ordered


def discover_nvblox_pointcloud_topics(
    topics: set[str],
    *,
    topic_types: dict[str, str | None] | None = None,
) -> list[str]:
    discovered: list[str] = []
    for topic in (*NVBLOX_REQUIRED_POINTCLOUD_TOPICS, *NVBLOX_OPTIONAL_ESDF_TOPICS):
        if topic not in topics:
            continue
        msg_type = (topic_types or {}).get(topic)
        if msg_type is not None and not _is_pointcloud2_type(msg_type):
            continue
        discovered.append(topic)
    for topic in sorted(topics):
        if not topic.startswith("/nvblox_node/back_projected_depth/"):
            continue
        msg_type = (topic_types or {}).get(topic)
        if msg_type is not None and not _is_pointcloud2_type(msg_type):
            continue
        if topic not in discovered:
            discovered.append(topic)
    return discovered


def _rgbd_visualization_probe_topics(topics: set[str]) -> list[str]:
    """Fast readiness probes — RGB-D PointCloud2 + odom only; nvblox is optional."""
    ordered: list[str] = []
    primary = WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic
    if primary in topics:
        ordered.append(primary)
    for candidate in discover_rgbd_pointcloud_topics(topics):
        if candidate not in ordered:
            ordered.append(candidate)
    for topic in ODOM_PREFLIGHT_TOPICS:
        if topic in topics and topic not in ordered:
            ordered.append(topic)
    return ordered


def _ros2_workspace():
    from pathlib import Path

    from backend.core.config.runtime import settings

    raw = settings.warehouse_ros2_ws.strip() or "ros2_ws"
    return Path(raw).expanduser().resolve()


def _topic_info(topic: str, ws) -> str | None:
    cmd = (
        f"source /opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash && "
        f"source {ws / 'install/setup.bash'} && "
        f"timeout 3 ros2 topic info {topic} -v"
    )
    try:
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
            env=ros_command_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "Type:" in line:
            return line.split("Type:", 1)[1].strip()
    return None


def _topic_has_message(topic: str, ws, *, timeout_s: float = 3.0) -> bool:
    """Check that at least one message arrives on topic (no hz averaging)."""
    cmd = (
        f"source /opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash && "
        f"source {ws / 'install/setup.bash'} && "
        f"timeout {max(2.5, timeout_s)} ros2 topic echo {topic} --once"
    )
    try:
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=max(4.0, timeout_s + 1.0),
            check=False,
            env=ros_command_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def probe_live_map_topic_types(
    *,
    topics: set[str] | None = None,
    quiet: bool = False,
) -> tuple[list[TopicTypeProbe], dict[str, str | None]]:
    ws = _ros2_workspace()
    if topics is None:
        try:
            topics = set(list_ros2_topics(ws))
        except RuntimeError as exc:
            logger.warning("Could not list ROS topics for type probe: %s", exc)
            topics = set()

    topic_types: dict[str, str | None] = {}
    probes: list[TopicTypeProbe] = []

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
    for topic in sorted(topics):
        if topic.startswith("/nvblox_node/back_projected_depth/"):
            probe_specs.append((topic, True, False, False))

    seen: set[str] = set()
    rgb_inputs_present = all(topic in topics for topic in RGBD_INPUT_TOPICS)

    for topic, expect_pc2, internal_layer, required in probe_specs:
        if topic in seen:
            continue
        seen.add(topic)
        present = topic in topics
        msg_type = _topic_info(topic, ws) if present else None
        if msg_type is not None:
            topic_types[topic] = msg_type
        probe = classify_topic_for_bridge(
            topic=topic,
            present=present,
            message_type=msg_type,
            expect_pointcloud2=expect_pc2,
            internal_layer=internal_layer,
        )
        if (
            topic == WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic
            and not present
            and rgb_inputs_present
        ):
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

    return probes, topic_types


def probe_nvblox_topic_types() -> list[TopicTypeProbe]:
    probes, _ = probe_live_map_topic_types()
    return probes


def _rgb_inputs_ready(topics: set[str], publishing: set[str]) -> tuple[bool, list[str]]:
    missing = [topic for topic in RGBD_INPUT_TOPICS if topic not in topics]
    publishing_inputs = [topic for topic in RGBD_INPUT_TOPICS if topic in publishing]
    odom_ready = all(topic in topics for topic in ODOM_PREFLIGHT_TOPICS)
    ready = (
        odom_ready
        and len(missing) == 0
        and len(publishing_inputs) >= max(3, len(RGBD_INPUT_TOPICS) - 1)
    )
    return ready, missing


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
            topics = set(await asyncio.to_thread(list_ros2_topics, ws))
        except RuntimeError:
            topics = set()

        rgbd_candidates = discover_rgbd_pointcloud_topics(topics)
        probe_topics = _rgbd_visualization_probe_topics(topics)
        publishing: set[str] = set()

        for topic in probe_topics:
            if topic not in topics:
                continue
            has_message = await asyncio.to_thread(
                _topic_has_message,
                topic,
                ws,
                timeout_s=3.0,
            )
            if has_message:
                publishing.add(topic)
                if (
                    first_rgbd_msg_at is None
                    and topic in rgbd_candidates
                ):
                    first_rgbd_msg_at = time.monotonic()
                    _note_mapping_startup("first_rgbd_pointcloud_msg_monotonic")

        rgbd_pointcloud_topic = next(
            (topic for topic in rgbd_candidates if topic in publishing),
            rgbd_candidates[0] if rgbd_candidates else None,
        )
        rgbd_pc_ready = bool(
            rgbd_pointcloud_topic and rgbd_pointcloud_topic in publishing
        )
        rgb_inputs_ready, missing_inputs = _rgb_inputs_ready(topics, publishing)

        if rgbd_pc_ready:
            _note_mapping_startup("rgbd_readiness_monotonic")
            last_probes, _ = probe_live_map_topic_types(topics=topics, quiet=True)
            last_warnings = [
                p.warning for p in last_probes if p.warning and p.topic in probe_topics
            ]
            nvblox_pc_topics = discover_nvblox_pointcloud_topics(topics)
            timing_ms = {
                "wait_for_rgbd_mapping_topics_ms": int(
                    (time.monotonic() - wait_started) * 1000
                ),
            }
            active = _active_mapping_startup_timing()
            if active is not None:
                timing_ms.update(active.as_dict())
            return MappingReadinessResult(
                ready=True,
                missing_topics=[],
                topic_probes=last_probes,
                warnings=last_warnings,
                rgbd_pointcloud_topic=rgbd_pointcloud_topic,
                rgbd_input_topics_ready=rgb_inputs_ready,
                nvblox_pointcloud_topics=nvblox_pc_topics,
                timing_ms=timing_ms,
            )

        if rgb_inputs_ready and RGBD_VISUALIZATION_TOPIC not in topics:
            _note_mapping_startup("rgbd_readiness_monotonic")
            last_probes, topic_types = probe_live_map_topic_types(
                topics=topics,
                quiet=True,
            )
            nvblox_pc_topics = discover_nvblox_pointcloud_topics(
                topics,
                topic_types=topic_types,
            )
            timing_ms = {
                "wait_for_rgbd_mapping_topics_ms": int(
                    (time.monotonic() - wait_started) * 1000
                ),
            }
            active = _active_mapping_startup_timing()
            if active is not None:
                timing_ms.update(active.as_dict())
            return MappingReadinessResult(
                ready=True,
                missing_topics=missing_inputs,
                topic_probes=last_probes,
                warnings=last_warnings,
                rgbd_pointcloud_topic=rgbd_pointcloud_topic,
                rgbd_input_topics_ready=True,
                nvblox_pointcloud_topics=nvblox_pc_topics,
                timing_ms=timing_ms,
            )

        await asyncio.sleep(max(0.15, poll_s))

    try:
        topics = set(await asyncio.to_thread(list_ros2_topics, ws))
    except RuntimeError:
        topics = set()
    last_probes, topic_types = probe_live_map_topic_types(topics=topics)
    _, missing_inputs = _rgb_inputs_ready(topics, set())
    rgbd_candidates = discover_rgbd_pointcloud_topics(topics, topic_types=topic_types)
    timing_ms = {
        "wait_for_rgbd_mapping_topics_ms": int(
            (time.monotonic() - wait_started) * 1000
        ),
    }
    active = _active_mapping_startup_timing()
    if active is not None:
        timing_ms.update(active.as_dict())
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
        nvblox_pointcloud_topics=discover_nvblox_pointcloud_topics(
            topics,
            topic_types=topic_types,
        ),
        timing_ms=timing_ms,
    )


async def probe_mapping_tf_degraded(
    *,
    parent_frame: str = "odom",
    child_frame: str = "iris_with_standoffs/base_link",
) -> dict[str, object]:
    """Best-effort TF probe for diagnostics; never gates takeoff."""
    from backend.modules.warehouse.service.sim_time_tf_readiness import _sourced_ros_cmd

    env = ros_command_env()
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            _sourced_ros_cmd(
                f"timeout 3.0 ros2 run tf2_ros tf2_echo {parent_frame} {child_frame}"
            ),
            env=env,
            capture_output=True,
            text=True,
            timeout=5.5,
        )
        stdout = result.stdout or ""
        ok = "At time" in stdout
        detail = None if ok else (result.stderr or stdout or "tf lookup failed")[:240]
        return {
            "tf_ok": ok,
            "parent_frame": parent_frame,
            "child_frame": child_frame,
            "degraded": not ok,
            "detail": detail,
        }
    except Exception as exc:
        return {
            "tf_ok": False,
            "parent_frame": parent_frame,
            "child_frame": child_frame,
            "degraded": True,
            "detail": str(exc)[:240],
        }


def resolve_colored_bridge_sources(
    *,
    topic_probes: dict[str, TopicTypeProbe] | None = None,
    topics: set[str] | None = None,
    rgbd_pointcloud_topic: str | None = None,
) -> dict[str, LiveMapSourceConfig]:
    if topics is None:
        ws = _ros2_workspace()
        try:
            topics = set(list_ros2_topics(ws))
        except RuntimeError:
            topics = set()

    _, topic_types = probe_live_map_topic_types(topics=topics, quiet=True)
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
            sources["nvblox_esdf"] = WAREHOUSE_LIVE_MAP_SOURCES["nvblox_esdf"]
        elif topic.startswith("/nvblox_node/back_projected_depth/"):
            back_projected_topic = topic

    # back_projected_depth is published in the camera optical frame. Using it for
    # nvblox_color produced ceiling-height artifacts when TF lookup failed silently.
    # The integrated color map comes from /nvblox_node/color_layer (VoxelBlockLayer,
    # world-frame voxel centers) via nvblox_layers_live_map_bridge.
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
