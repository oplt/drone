from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import shlex
import subprocess
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
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

# Cached RGB-D readiness from background preflight warm-up (S1 follow-up).
_rgbd_readiness_cache: MappingReadinessResult | None = None
_rgbd_readiness_cache_at: float = 0.0
_rgbd_warmup_lock = asyncio.Lock()
_rgbd_warmup_running = False

# Cached live-map topic-type probe (speeds bridge subscription setup).
_topic_probe_cache: tuple[list[TopicTypeProbe], dict[str, str | None]] | None = None
_topic_probe_cache_at: float = 0.0

TopicBridgeKind = Literal[
    "pointcloud2",
    "internal_layer",
    "missing",
    "wrong_type",
]

_MAX_TOPIC_INFO_WORKERS = 8
_MAX_MESSAGE_PROBE_CONCURRENCY = 4


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
        rgbd_pc_probe = probes_by_topic.get(self.rgbd_pointcloud_topic) if self.rgbd_pointcloud_topic else None
        return {
            "rgbd_input_ready": self.rgbd_input_topics_ready,
            "rgbd_colored_pointcloud_ready": bool(
                rgbd_pc_probe is not None and rgbd_pc_probe.ok_for_pointcloud_bridge
            ),
            "nvblox_esdf_ready": any(
                probe.topic.endswith("static_esdf_pointcloud") and probe.ok_for_pointcloud_bridge
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


def _rgbd_readiness_cache_ttl_s() -> float:
    from backend.core.config.runtime import settings

    return max(0.0, float(getattr(settings, "warehouse_rgbd_readiness_cache_ttl_s", 30.0)))


def _topic_probe_cache_ttl_s() -> float:
    from backend.core.config.runtime import settings

    return max(0.0, float(getattr(settings, "warehouse_live_map_topic_probe_cache_ttl_s", 15.0)))


def _store_rgbd_readiness_cache(result: MappingReadinessResult) -> None:
    global _rgbd_readiness_cache, _rgbd_readiness_cache_at
    if result.ready:
        _rgbd_readiness_cache = result
        _rgbd_readiness_cache_at = time.monotonic()


def peek_cached_rgbd_readiness(*, max_age_s: float | None = None) -> MappingReadinessResult | None:
    """Return a recent successful RGB-D readiness result, if any."""
    if _rgbd_readiness_cache is None:
        return None
    ttl = _rgbd_readiness_cache_ttl_s() if max_age_s is None else max(0.0, max_age_s)
    if ttl <= 0.0:
        return None
    if (time.monotonic() - _rgbd_readiness_cache_at) >= ttl:
        return None
    return _rgbd_readiness_cache


async def warm_rgbd_readiness_background(*, timeout_s: float = 90.0) -> None:
    """Poll RGB-D topics in the background during preflight warm-up."""
    global _rgbd_warmup_running

    cached = peek_cached_rgbd_readiness()
    if cached is not None and cached.ready:
        return

    async with _rgbd_warmup_lock:
        cached = peek_cached_rgbd_readiness()
        if cached is not None and cached.ready:
            return
        if _rgbd_warmup_running:
            return
        _rgbd_warmup_running = True

    try:
        result = await wait_for_rgbd_mapping_topics(timeout_s=max(5.0, timeout_s))
        if result.ready:
            logger.info(
                "Background RGB-D readiness warm-up complete (topic=%r)",
                result.rgbd_pointcloud_topic,
            )
    except Exception:
        logger.debug("Background RGB-D readiness warm-up failed", exc_info=True)
    finally:
        async with _rgbd_warmup_lock:
            _rgbd_warmup_running = False


async def warm_live_map_ros_graph() -> None:
    """Pre-run topic probes and rclpy init so bridge start is faster at takeoff."""

    def _warm_sync() -> None:
        probe_live_map_topic_types(quiet=True, use_cache=True)
        try:
            import rclpy

            if not rclpy.ok():
                rclpy.init(args=None)
        except Exception:
            logger.debug("rclpy pre-init during live-map warm-up skipped", exc_info=True)

    await asyncio.to_thread(_warm_sync)


def _note_mapping_startup(mark: str) -> None:
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import note_mapping_startup

        note_mapping_startup(mark)
    except ModuleNotFoundError as exc:
        logger.warning("Optional mapping startup timing unavailable: %s", exc)
    except Exception:
        logger.debug("Could not record mapping startup mark=%s", mark, exc_info=True)


def _active_mapping_startup_timing():
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import active_mapping_startup_timing

        return active_mapping_startup_timing()
    except ModuleNotFoundError:
        return None
    except Exception:
        logger.debug("Could not read active mapping startup timing", exc_info=True)
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


def _ros2_workspace() -> Path:
    from backend.core.config.runtime import settings

    raw = str(getattr(settings, "warehouse_ros2_ws", "") or "").strip() or "ros2_ws"
    return Path(raw).expanduser().resolve()


def _source_setup(ws: Path) -> str:
    return (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {shlex.quote(str(ws / 'install/setup.bash'))}"
    )


def _run_sourced_ros_command(command: str, *, ws: Path, timeout_s: float) -> subprocess.CompletedProcess[str] | None:
    cmd = f"{_source_setup(ws)} && {command}"
    try:
        return subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=max(0.5, timeout_s),
            check=False,
            env=ros_command_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _topic_info(topic: str, ws: Path) -> str | None:
    result = _run_sourced_ros_command(
        f"timeout 3 ros2 topic info {shlex.quote(topic)} -v",
        ws=ws,
        timeout_s=5.0,
    )
    if result is None or result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "Type:" in line:
            return line.split("Type:", 1)[1].strip()
    return None


def _topic_has_message(topic: str, ws: Path, *, timeout_s: float = 3.0) -> bool:
    """Check that at least one message arrives on topic (no hz averaging)."""
    bounded_timeout = max(0.5, float(timeout_s))
    result = _run_sourced_ros_command(
        f"timeout {max(0.5, bounded_timeout):.3f} ros2 topic echo {shlex.quote(topic)} --once",
        ws=ws,
        timeout_s=bounded_timeout + 1.0,
    )
    return bool(result is not None and result.returncode == 0 and (result.stdout or "").strip())


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
        future_by_topic = {pool.submit(_topic_info, topic, ws): topic for topic in present_topics}
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
    global _topic_probe_cache, _topic_probe_cache_at

    ttl = _topic_probe_cache_ttl_s()
    if use_cache and ttl > 0.0 and _topic_probe_cache is not None and topics is None:
        if (time.monotonic() - _topic_probe_cache_at) < ttl:
            return _topic_probe_cache

    ws = _ros2_workspace()
    if topics is None:
        try:
            topics = set(list_ros2_topics(ws))
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
        _topic_probe_cache = result
        _topic_probe_cache_at = time.monotonic()
    return result


def probe_nvblox_topic_types() -> list[TopicTypeProbe]:
    probes, _ = probe_live_map_topic_types()
    return probes


def _rgb_inputs_ready(topics: set[str], publishing: set[str]) -> tuple[bool, list[str]]:
    missing = [topic for topic in RGBD_INPUT_TOPICS if topic not in topics]
    publishing_inputs = [topic for topic in RGBD_INPUT_TOPICS if topic in publishing]
    odom_ready = all(topic in topics for topic in ODOM_PREFLIGHT_TOPICS)
    ready = odom_ready and len(missing) == 0 and len(publishing_inputs) >= max(3, len(RGBD_INPUT_TOPICS) - 1)
    return ready, missing


async def _probe_messages(
    *,
    topics: list[str],
    ws: Path,
    per_topic_timeout_s: float,
) -> set[str]:
    semaphore = asyncio.Semaphore(_MAX_MESSAGE_PROBE_CONCURRENCY)

    async def _one(topic: str) -> tuple[str, bool]:
        async with semaphore:
            return topic, await asyncio.to_thread(_topic_has_message, topic, ws, timeout_s=per_topic_timeout_s)

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
            topics = set(await asyncio.to_thread(list_ros2_topics, ws))
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
            last_probes, topic_types = probe_live_map_topic_types(topics=topics, quiet=True)
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
            last_probes, topic_types = probe_live_map_topic_types(topics=topics, quiet=True)
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
        topics = set(await asyncio.to_thread(list_ros2_topics, ws))
    except RuntimeError:
        topics = set()
    last_probes, topic_types = await asyncio.to_thread(probe_live_map_topic_types, topics=topics)
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
                "timeout 3.0 ros2 run tf2_ros tf2_echo "
                f"{shlex.quote(parent_frame)} {shlex.quote(child_frame)}"
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

    if topic_probes:
        topic_types = {
            topic: probe.message_type
            for topic, probe in topic_probes.items()
            if probe.message_type is not None
        }
    else:
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
