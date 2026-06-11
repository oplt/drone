from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any

from backend.infrastructure.warehouse.bridge_config import (
    list_ros2_topics,
    ros_command_env,
)
from backend.modules.warehouse.service.map_source_config import (
    LIDAR_PREFLIGHT_TOPICS,
    NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
    ODOM_PREFLIGHT_TOPICS,
    RGBD_PREFLIGHT_TOPICS,
    WAREHOUSE_LIVE_MAP_SOURCES,
    NVBLOX_INTERNAL_LAYER_TOPICS,
    NVBLOX_OUTPUT_TOPICS,
)
from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker
from backend.modules.warehouse.service.pointcloud2_parser import parse_pointcloud2_yaml
from backend.modules.warehouse.service.live_map_bridge import _read_pointcloud2_yaml

logger = logging.getLogger(__name__)


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


def _ros2_workspace() -> Any:
    from pathlib import Path

    from backend.core.config.runtime import settings

    raw = settings.warehouse_ros2_ws.strip() or "ros2_ws"
    return Path(raw).expanduser().resolve()


def _topic_hz(topic: str, ws: Any) -> float | None:
    cmd = (
        f"source /opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash && "
        f"source {ws / 'install/setup.bash'} && "
        f"timeout 3 ros2 topic hz {topic} --window 5"
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

    for line in result.stdout.splitlines():
        if "average rate:" in line:
            try:
                return float(line.split("average rate:")[1].split()[0])
            except (IndexError, ValueError):
                return None
    return None


def _check_tf_chain(ws: Any) -> tuple[bool, str]:
    frames = [
        ("odom", "iris_with_standoffs/base_link"),
        ("iris_with_standoffs/base_link", "front_rgbd_camera_link"),
        ("odom", "front_rgbd_camera_link"),
    ]
    missing: list[str] = []
    for source, target in frames:
        cmd = (
            f"source /opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash && "
            f"source {ws / 'install/setup.bash'} && "
            f"timeout 2 ros2 run tf2_ros tf2_echo {source} {target}"
        )
        try:
            result = subprocess.run(
                ["bash", "-lc", cmd],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
                env=ros_command_env(),
            )
        except (OSError, subprocess.TimeoutExpired):
            missing.append(f"{source}->{target}")
            continue

        if result.returncode != 0 or "Failure" in result.stderr:
            missing.append(f"{source}->{target}")

    if missing:
        return False, f"Missing TF: {', '.join(missing)}"
    return True, "TF chain odom/base_link/RGB-D available"


def _check_rgbd_color_fields(ws: Any) -> tuple[bool | None, str]:
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


async def run_live_map_diagnostics() -> WarehouseLiveMapDiagnostics:
    ws = _ros2_workspace()
    diagnostics = WarehouseLiveMapDiagnostics()

    try:
        topics = set(list_ros2_topics(ws))
    except RuntimeError as exc:
        diagnostics.warnings.append(f"Could not list ROS topics: {exc}")
        topics = set()

    nvblox_status_tracker.note_topic_list(topics)
    diagnostics.nvblox_topics_present = any(
        topic in topics for topic in NVBLOX_OUTPUT_TOPICS
    )

    check_topics = (
        *RGBD_PREFLIGHT_TOPICS,
        *LIDAR_PREFLIGHT_TOPICS,
        *ODOM_PREFLIGHT_TOPICS,
        "/tf",
        *NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
        *NVBLOX_INTERNAL_LAYER_TOPICS[:1],
    )

    publishing: dict[str, bool] = {}
    for topic in check_topics:
        present = topic in topics or topic == "/tf"
        hz = await asyncio.to_thread(_topic_hz, topic, ws) if present else None
        is_publishing = hz is not None and hz > 0.05
        publishing[topic] = is_publishing

        if topic.startswith("/nvblox_node/") and is_publishing:
            nvblox_status_tracker.note_message(topic)
            diagnostics.nvblox_has_output = True

        message = "publishing" if is_publishing else ("listed" if present else "missing")
        if hz is not None:
            message = f"{message} ({hz:.1f} Hz)"
        diagnostics.topics.append(
            TopicCheckResult(topic=topic, publishing=is_publishing, message=message)
        )

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

    rgbd_live = publishing.get(RGBD_PREFLIGHT_TOPICS[0], False)
    lidar_live = publishing.get(LIDAR_PREFLIGHT_TOPICS[0], False)
    diagnostics.only_lidar_available = lidar_live and not rgbd_live and not diagnostics.nvblox_has_output
    if diagnostics.only_lidar_available:
        diagnostics.warnings.append("Only raw Mid360 LiDAR is currently publishing map data")

    if diagnostics.nvblox_topics_present and not diagnostics.nvblox_has_output:
        diagnostics.warnings.append("nvBlox topics exist but no recent output messages")

    diagnostics.nvblox_status = nvblox_status_tracker.status()
    return diagnostics
