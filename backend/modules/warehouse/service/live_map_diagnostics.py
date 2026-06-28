from __future__ import annotations

import asyncio
import copy
import logging
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.infrastructure.warehouse.bridge_config import (
    list_ros2_topics,
    ros_command_env,
)
from backend.modules.warehouse.service.map_source_config import (
    LIDAR_PREFLIGHT_TOPICS,
    NVBLOX_INTERNAL_LAYER_TOPICS,
    NVBLOX_OUTPUT_TOPICS,
    NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
    ODOM_PREFLIGHT_TOPICS,
    RGBD_PREFLIGHT_TOPICS,
    WAREHOUSE_LIVE_MAP_SOURCES,
)
from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker
from backend.modules.warehouse.service.pointcloud2_parser import parse_pointcloud2_yaml
from backend.modules.warehouse.service.live_map_bridge import _read_pointcloud2_yaml

logger = logging.getLogger(__name__)

_AVERAGE_RATE_RE = re.compile(r"average rate:\s*([-+0-9.eE]+)")
_DEFAULT_HZ_TIMEOUT_S = 5.0
_DEFAULT_TF_TIMEOUT_S = 4.0
_MAX_CONCURRENT_ROS_PROBES = 4
_DIAGNOSTICS_CACHE: tuple[float, WarehouseLiveMapDiagnostics] | None = None
_DIAGNOSTICS_CACHE_LOCK = asyncio.Lock()


@dataclass
class TopicCheckResult:
    topic: str
    publishing: bool
    message: str


@dataclass
class WarehouseLiveMapDiagnostics:
    topics: list[TopicCheckResult] = field(default_factory=list)
    tf_ok: bool = False
    tf_message: str = ""
    rgbd_has_rgb: bool | None = None
    rgbd_message: str = ""
    nvblox_topics_present: bool = False
    nvblox_has_output: bool = False
    nvblox_status: str = "off"
    only_lidar_available: bool = False
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "topics": [
                {"topic": item.topic, "publishing": item.publishing, "message": item.message}
                for item in self.topics
            ],
            "tf_ok": self.tf_ok,
            "tf_message": self.tf_message,
            "rgbd_has_rgb": self.rgbd_has_rgb,
            "rgbd_message": self.rgbd_message,
            "nvblox_topics_present": self.nvblox_topics_present,
            "nvblox_has_output": self.nvblox_has_output,
            "nvblox_status": self.nvblox_status,
            "only_lidar_available": self.only_lidar_available,
            "warnings": self.warnings,
        }


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
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("ROS diagnostic command failed: %s", exc)
        return None


def _topic_hz(topic: str, ws: Path) -> float | None:
    safe_topic = shlex.quote(str(topic))
    result = _run_sourced_ros_command(
        f"timeout 3 ros2 topic hz {safe_topic} --window 5",
        ws=ws,
        timeout_s=_DEFAULT_HZ_TIMEOUT_S,
    )
    if result is None:
        return None

    for line in result.stdout.splitlines():
        match = _AVERAGE_RATE_RE.search(line)
        if not match:
            continue
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _check_tf_pair(ws: Path, source: str, target: str) -> bool:
    result = _run_sourced_ros_command(
        "timeout 2 ros2 run tf2_ros tf2_echo "
        f"{shlex.quote(source)} {shlex.quote(target)}",
        ws=ws,
        timeout_s=_DEFAULT_TF_TIMEOUT_S,
    )
    if result is None:
        return False
    return result.returncode == 0 and "Failure" not in (result.stderr or "")


def _check_tf_chain(ws: Path) -> tuple[bool, str]:
    frames = [
        ("odom", "base_link"),
        ("base_link", "lidar_link"),
        ("base_link", "camera_link"),
        ("camera_link", "camera_optical_frame"),
        ("base_link", "imu_link"),
        ("odom", "camera_optical_frame"),
    ]
    missing = [f"{source}->{target}" for source, target in frames if not _check_tf_pair(ws, source, target)]
    if missing:
        return False, f"Missing TF: {', '.join(missing)}"
    return True, "Stable odom/base_link/sensor TF tree available"


def _check_rgbd_color_fields(ws: Path) -> tuple[bool | None, str]:
    topic = WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic
    payload = _read_pointcloud2_yaml(topic=topic, ws=ws)
    if payload is None:
        return None, "RGB-D points topic has no recent message"

    parsed = parse_pointcloud2_yaml(payload, max_points=100, downsample=False)
    if parsed is None:
        return None, "Could not parse RGB-D PointCloud2"

    if parsed.has_rgb:
        return True, "RGB-D points include RGB fields"
    return False, "RGB-D points have no rgb/rgba/r/g/b fields; height/distance coloring will be used"


def _dedupe_topics(topics: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for topic in topics:
        token = str(topic or "").strip()
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


async def _probe_topic_hz_bounded(topic: str, ws: Path, semaphore: asyncio.Semaphore) -> tuple[str, float | None]:
    async with semaphore:
        return topic, await asyncio.to_thread(_topic_hz, topic, ws)


async def _collect_live_map_diagnostics() -> WarehouseLiveMapDiagnostics:
    ws = _ros2_workspace()
    diagnostics = WarehouseLiveMapDiagnostics()

    try:
        topics = set(await asyncio.to_thread(list_ros2_topics, ws))
    except RuntimeError as exc:
        diagnostics.warnings.append(f"Could not list ROS topics: {exc}")
        topics = set()

    nvblox_status_tracker.note_topic_list(topics)
    diagnostics.nvblox_topics_present = any(topic in topics for topic in NVBLOX_OUTPUT_TOPICS)

    check_topics = _dedupe_topics(
        (
            *RGBD_PREFLIGHT_TOPICS,
            *LIDAR_PREFLIGHT_TOPICS,
            *ODOM_PREFLIGHT_TOPICS,
            "/tf",
            *NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
            *NVBLOX_INTERNAL_LAYER_TOPICS[:1],
        )
    )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_ROS_PROBES)
    hz_by_topic: dict[str, float | None] = {}
    probe_tasks = [
        _probe_topic_hz_bounded(topic, ws, semaphore)
        for topic in check_topics
        if topic in topics or topic == "/tf"
    ]
    for topic, hz in await asyncio.gather(*probe_tasks):
        hz_by_topic[topic] = hz

    publishing: dict[str, bool] = {}
    for topic in check_topics:
        present = topic in topics or topic == "/tf"
        hz = hz_by_topic.get(topic)
        is_publishing = hz is not None and hz > 0.05
        publishing[topic] = is_publishing

        if topic.startswith("/nvblox_node/") and is_publishing:
            nvblox_status_tracker.note_message(topic)
            diagnostics.nvblox_has_output = True

        message = "publishing" if is_publishing else ("listed" if present else "missing")
        if hz is not None:
            message = f"{message} ({hz:.1f} Hz)"
        diagnostics.topics.append(TopicCheckResult(topic=topic, publishing=is_publishing, message=message))

    tf_ok, tf_message = await asyncio.to_thread(_check_tf_chain, ws)
    diagnostics.tf_ok = tf_ok
    diagnostics.tf_message = tf_message
    if not tf_ok:
        nvblox_status_tracker.note_tf_depth_failure(True)
        diagnostics.warnings.append(tf_message)

    rgbd_has_rgb, rgbd_message = await asyncio.to_thread(_check_rgbd_color_fields, ws)
    diagnostics.rgbd_has_rgb = rgbd_has_rgb
    diagnostics.rgbd_message = rgbd_message
    if rgbd_has_rgb is False:
        diagnostics.warnings.append(rgbd_message)

    rgbd_live = publishing.get(RGBD_PREFLIGHT_TOPICS[0], False) if RGBD_PREFLIGHT_TOPICS else False
    lidar_live = publishing.get(LIDAR_PREFLIGHT_TOPICS[0], False) if LIDAR_PREFLIGHT_TOPICS else False
    diagnostics.only_lidar_available = lidar_live and not rgbd_live and not diagnostics.nvblox_has_output
    if diagnostics.only_lidar_available:
        diagnostics.warnings.append("Only raw Mid360 LiDAR is currently publishing map data")

    if diagnostics.nvblox_topics_present and not diagnostics.nvblox_has_output:
        diagnostics.warnings.append("nvBlox topics exist but no recent output messages")

    diagnostics.nvblox_status = nvblox_status_tracker.status()
    return diagnostics


def _diagnostics_cache_ttl_s() -> float:
    from backend.core.config.runtime import settings

    return max(
        0.0,
        float(getattr(settings, "warehouse_live_map_diagnostics_cache_ttl_s", 45.0)),
    )


def clear_live_map_diagnostics_cache() -> None:
    global _DIAGNOSTICS_CACHE

    _DIAGNOSTICS_CACHE = None


def _cached_diagnostics(now: float, ttl_s: float) -> WarehouseLiveMapDiagnostics | None:
    if _DIAGNOSTICS_CACHE is None or ttl_s <= 0:
        return None
    cached_at, report = _DIAGNOSTICS_CACHE
    if now - cached_at >= ttl_s:
        return None
    return copy.deepcopy(report)


async def run_live_map_diagnostics(
    *,
    force: bool = False,
    cache_ttl_s: float | None = None,
) -> WarehouseLiveMapDiagnostics:
    """Return cached ROS diagnostics and coalesce concurrent refresh probes."""

    ttl_s = _diagnostics_cache_ttl_s() if cache_ttl_s is None else max(0.0, cache_ttl_s)
    now = time.monotonic()
    if not force:
        cached = _cached_diagnostics(now, ttl_s)
        if cached is not None:
            return cached

    async with _DIAGNOSTICS_CACHE_LOCK:
        now = time.monotonic()
        if not force:
            cached = _cached_diagnostics(now, ttl_s)
            if cached is not None:
                return cached

        report = await _collect_live_map_diagnostics()
        global _DIAGNOSTICS_CACHE
        _DIAGNOSTICS_CACHE = (time.monotonic(), copy.deepcopy(report))
        return report
