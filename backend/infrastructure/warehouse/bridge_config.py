"""Warehouse Gazebo ↔ ROS bridge config and topic health probes.

Single source of truth: ``ros2_ws/src/drone_gz_bridge/config/warehouse_bridge.yaml``.
Preflight compares live ``ros2 topic list`` / ``gz topic -l`` output against that file.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backend.core.config.runtime import settings

GZ_TO_ROS = "GZ_TO_ROS"
ROS_TO_GZ = "ROS_TO_GZ"


def _raw_lidar_required() -> bool:
    return bool(
        getattr(settings, "warehouse_live_map_raw_lidar_enabled", False)
        or getattr(settings, "warehouse_include_raw_lidar_preview", False)
        or getattr(settings, "warehouse_persist_raw_lidar_layer", False)
    )


@dataclass(frozen=True)
class BridgeTopicMapping:
    ros_topic_name: str
    gz_topic_name: str
    ros_type_name: str = ""
    gz_type_name: str = ""
    direction: str = GZ_TO_ROS


def bridge_config_path(ros2_ws: Path) -> Path:
    return ros2_ws / "src/drone_gz_bridge/config/warehouse_bridge.yaml"


def load_bridge_config(ros2_ws: Path) -> list[BridgeTopicMapping]:
    path = bridge_config_path(ros2_ws)
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    mappings: list[BridgeTopicMapping] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ros_topic = str(entry.get("ros_topic_name") or "").strip()
        gz_topic = str(entry.get("gz_topic_name") or "").strip()
        if not ros_topic or not gz_topic:
            continue
        mappings.append(
            BridgeTopicMapping(
                ros_topic_name=ros_topic,
                gz_topic_name=gz_topic,
                ros_type_name=str(entry.get("ros_type_name") or "").strip(),
                gz_type_name=str(entry.get("gz_type_name") or "").strip(),
                direction=str(entry.get("direction") or GZ_TO_ROS).strip(),
            )
        )
    return mappings


def gz_to_ros_mappings(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [m for m in mappings if m.direction == GZ_TO_ROS]


def ros_command_env() -> dict[str, str]:
    env = dict(os.environ)
    env["ROS_DOMAIN_ID"] = ros_domain_id()
    env.setdefault("ROS_LOG_DIR", "/tmp/warehouse_ros_logs")
    # FastDDS shared-memory ports frequently remain locked after Gazebo/ROS
    # restarts in local dev, producing RTPS_TRANSPORT_SHM errors. UDP keeps
    # discovery/data flow reliable for this single-machine sim stack.
    env.setdefault("FASTDDS_BUILTIN_TRANSPORTS", "UDPv4")
    venv_bin = None
    if env.get("VIRTUAL_ENV"):
        venv_bin = str(Path(env["VIRTUAL_ENV"]) / "bin")
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if venv_bin:
        env["PATH"] = ":".join(
            part for part in env.get("PATH", "").split(":") if part != venv_bin
        )
    return env


def configure_embedded_ros_environment() -> None:
    """Apply transport settings before the API process creates an rclpy context.

    CLI probes and launched ROS processes already use ``ros_command_env``. The
    in-process live-map subscribers must use the same DDS domain and transport;
    otherwise FastDDS may select stale shared-memory ports and receive no data.
    """
    env = ros_command_env()
    for name in (
        "ROS_DOMAIN_ID",
        "ROS_AUTOMATIC_DISCOVERY_RANGE",
        "RMW_IMPLEMENTATION",
        "FASTDDS_BUILTIN_TRANSPORTS",
    ):
        value = env.get(name)
        if value:
            os.environ[name] = value


def ros_domain_id() -> str:
    return settings.ros_domain_id


def preflight_core_ros_topics(ros2_ws: Path) -> set[str]:
    """ROS topic names required before warehouse preflight can pass (from yaml)."""
    bridged = gz_to_ros_mappings(load_bridge_config(ros2_ws.resolve()))
    names: set[str] = set()
    for entry in (
        *_preflight_odometry(bridged),
        *_preflight_imu(bridged),
        *_preflight_rgbd(bridged),
    ):
        names.add(entry.ros_topic_name)
    return names


def list_ros2_topics_with_retry(
    ros2_ws: Path,
    *,
    attempts: int | None = None,
    pause_s: float | None = None,
    required_topics: set[str] | None = None,
) -> set[str]:
    """List ROS topics; retry until required topics appear or attempts exhaust."""
    if attempts is None:
        attempts = max(1, settings.warehouse_bridge_topic_probe_attempts)
    if pause_s is None:
        pause_s = settings.warehouse_bridge_topic_probe_pause_s

    ws = ros2_ws.resolve()
    last: set[str] = set()
    for attempt in range(attempts):
        try:
            last = list_ros2_topics(ws)
        except RuntimeError:
            last = set()
        if required_topics:
            ready = required_topics.issubset(last)
        else:
            ready = any(topic.startswith("/warehouse/") for topic in last)
        if ready:
            return last
        if attempt + 1 < attempts:
            time.sleep(max(0.2, pause_s))
    return last


def list_ros2_topics(ros2_ws: Path) -> set[str]:
    ws = ros2_ws.resolve()
    setup = ws / "install" / "setup.bash"
    if not setup.exists():
        raise RuntimeError(f"ROS 2 workspace is not built: {setup}")
    cmd = (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {setup} && "
        "ros2 topic list --no-daemon"
    )
    result = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=str(ws),
        capture_output=True,
        timeout=8,
        check=False,
        env=ros_command_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return {
        line.strip()
        for line in result.stdout.decode(errors="replace").splitlines()
        if line.strip()
    }


_PUBLISHER_COUNT_SCRIPT = """
import json, sys, time
import rclpy
from rclpy.node import Node

rclpy.init()
node = Node("warehouse_publisher_probe")
topics = json.loads(sys.argv[1])
deadline = time.monotonic() + 3.0
counts = {}
while True:
    counts = {topic: len(node.get_publishers_info_by_topic(topic)) for topic in topics}
    if all(count > 0 for count in counts.values()) or time.monotonic() >= deadline:
        break
    time.sleep(0.2)
print(json.dumps(counts))
node.destroy_node()
rclpy.shutdown()
"""


def count_topic_publishers(
    ros2_ws: Path,
    topics: set[str],
    *,
    timeout_s: float = 8.0,
) -> dict[str, int]:
    """Return publisher counts for all topics with one ROS subprocess.

    ``ros2 topic list`` can show topics created by subscribers, so preflight
    must verify publishers. Doing one ``ros2 topic info`` per topic was slow
    enough to make readiness time out; this rclpy probe performs one DDS
    discovery pass and returns all counts.
    """
    if not topics:
        return {}
    ws = ros2_ws.resolve()
    setup = ws / "install" / "setup.bash"
    if not setup.exists():
        return {}
    cmd = (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {setup} && "
        'python3 -c "$PROBE_SCRIPT" "$PROBE_TOPICS"'
    )
    env = ros_command_env()
    env["PROBE_SCRIPT"] = _PUBLISHER_COUNT_SCRIPT
    env["PROBE_TOPICS"] = json.dumps(sorted(topics))
    try:
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            return {}
        return {
            str(topic): int(count)
            for topic, count in parsed.items()
            if isinstance(count, int)
        }
    return {}


def quick_ros_bridge_check(ros2_ws: Path) -> tuple[bool | None, str]:
    """Lightweight bridge-up check used before starting the bridge process."""
    ws = ros2_ws.resolve()
    setup = ws / "install" / "setup.bash"
    if not setup.exists():
        return False, f"ROS 2 workspace is not built: {setup}"
    try:
        core_required = preflight_core_ros_topics(ws)
        topics = list_ros2_topics_with_retry(
            ws,
            attempts=2,
            pause_s=1.0,
            required_topics=core_required,
        )
        publisher_counts = count_topic_publishers(ws, core_required | {"/clock"})
    except FileNotFoundError:
        return False, "bash is not available; cannot probe ROS 2."
    except subprocess.TimeoutExpired:
        return None, "ROS 2 topic probe timed out."
    except RuntimeError as exc:
        return False, str(exc)
    if core_required.issubset(topics) and all(
        publisher_counts.get(topic, 0) > 0 for topic in core_required
    ):
        return True, f"ROS bridge core topics are present ({len(core_required)} required)."

    missing_core = sorted(core_required - topics)
    warehouse_topics = [topic for topic in topics if topic.startswith("/warehouse/")]
    if warehouse_topics:
        preview = ", ".join(missing_core[:4])
        suffix = "…" if len(missing_core) > 4 else ""
        return (
            None,
            "ROS graph has partial warehouse topics, but bridge core topics are "
            f"still missing: {preview}{suffix}. Start warehouse_bridge.launch.py.",
        )
    return None, "ROS graph reachable, but no /warehouse topics are publishing yet."


def list_gz_topics() -> tuple[set[str], str | None]:
    result = subprocess.run(
        ["bash", "-lc", "gz topic -l"],
        capture_output=True,
        timeout=3,
        check=False,
        env=ros_command_env(),
    )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        return set(), detail or "gz topic -l failed."
    return {
        line.strip()
        for line in result.stdout.decode(errors="replace").splitlines()
        if line.strip()
    }, None


def _preflight_odometry(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [m for m in mappings if m.ros_type_name == "nav_msgs/msg/Odometry"]


def _preflight_rgbd(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [
        m
        for m in mappings
        if m.ros_type_name == "sensor_msgs/msg/Image"
        and "/rgbd/" in m.ros_topic_name
        and (
            m.ros_topic_name.endswith("/image")
            or m.ros_topic_name.endswith("/depth_image")
        )
    ]


def _preflight_imu(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [m for m in mappings if m.ros_type_name == "sensor_msgs/msg/Imu"]


def _preflight_lidar(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [m for m in mappings if m.ros_type_name == "sensor_msgs/msg/PointCloud2"]


def _preflight_stereo_images(
    mappings: list[BridgeTopicMapping],
) -> tuple[BridgeTopicMapping | None, BridgeTopicMapping | None]:
    stereo = [
        m
        for m in mappings
        if m.ros_type_name == "sensor_msgs/msg/Image"
        and "/warehouse/stereo/" in m.ros_topic_name
        and m.ros_topic_name.endswith("/image")
    ]
    left = next((m for m in stereo if "/left/" in m.ros_topic_name), None)
    right = next((m for m in stereo if "/right/" in m.ros_topic_name), None)
    return left, right


def _topic_diag(*, topic: str | None, healthy: bool) -> dict[str, Any]:
    name = str(topic or "")
    return {
        "expected": name or None,
        "matched": name if healthy and name else None,
        "healthy": healthy,
        "readiness_state": "ok" if healthy else "missing",
    }


def bridge_probe_to_components(overlay: dict[str, Any]) -> dict[str, Any]:
    """Map a ``probe_bridge_topics`` payload into preflight component flags."""
    ros_topics = set(overlay.get("listed_ros_topics") or overlay.get("ros_topics") or [])

    rgb_topic = str(overlay.get("rgb_topic") or "")
    depth_topic = str(overlay.get("depth_topic") or "")
    imu_topic = str(overlay.get("imu_topic") or "")
    odom_topic = str(overlay.get("odometry_topic") or "")
    lidar_topic = str(overlay.get("lidar_topic") or "")
    stereo_left = str(overlay.get("stereo_left_topic") or "")
    stereo_right = str(overlay.get("stereo_right_topic") or "")

    def _ready(flag_key: str, topic: str) -> bool:
        flag = overlay.get(flag_key)
        if flag is not None:
            return bool(flag)
        return bool(topic) and topic in ros_topics

    rgb_ok = _ready("rgb_healthy", rgb_topic)
    depth_ok = _ready("depth_healthy", depth_topic)
    imu_ok = _ready("imu_healthy", imu_topic)
    odom_ok = _ready("odometry_healthy", odom_topic) or bool(overlay.get("local_position_ok"))
    lidar_required = _raw_lidar_required()
    lidar_ok_raw = _ready("lidar_healthy", lidar_topic) or bool(overlay.get("lidar_ok"))
    lidar_ok = lidar_ok_raw if lidar_required or lidar_ok_raw else None
    stereo_left_ok = _ready("stereo_left_healthy", stereo_left)
    stereo_right_ok = _ready("stereo_right_healthy", stereo_right)
    tf_ok = bool(overlay.get("tf_ok"))
    slam_ok = bool(overlay.get("slam_ready") or overlay.get("slam_tracking_ok"))
    ros_graph_ok = bool(overlay.get("ros_graph_healthy")) or bool(ros_topics)
    rgb_depth_imu_ok = (
        bool(overlay["rgb_depth_imu_ok"])
        if overlay.get("rgb_depth_imu_ok") is not None
        else (rgb_ok and depth_ok and imu_ok)
    )
    sensors_ok = (
        bool(overlay["sensors_ok"])
        if overlay.get("sensors_ok") is not None
        else rgb_depth_imu_ok
    )
    nvblox_ok = overlay.get("nvblox_ok")

    return {
        **{
            key: value
            for key, value in overlay.items()
            if key
            not in {
                "topic_diagnostics",
            }
        },
        "ros_graph": ros_graph_ok,
        "ros2_graph": ros_graph_ok,
        "ros2_cli": ros_graph_ok,
        "camera_topics": rgb_depth_imu_ok,
        "stereo_camera": rgb_depth_imu_ok,
        "imu_healthy": imu_ok,
        "imu": imu_ok,
        "imu_topic": imu_ok,
        "raw_lidar_healthy": lidar_ok,
        "lidar_ok": lidar_ok,
        "tf_tree": tf_ok,
        "tf": tf_ok,
        "visual_slam_healthy": slam_ok,
        "visual_slam": slam_ok,
        "vslam": slam_ok,
        "local_odometry_healthy": odom_ok,
        "local_position_ok": odom_ok,
        "odometry_healthy": odom_ok,
        "nvblox_healthy": nvblox_ok is True,
        "nvblox": nvblox_ok is True,
        "nvblox_warming_up": nvblox_ok is not True,
        "listed_topics": sorted(ros_topics),
        "odometry_topic": odom_topic or None,
        "topic_diagnostics": {
            "rgb_image": _topic_diag(topic=rgb_topic, healthy=rgb_ok),
            "depth_image": _topic_diag(topic=depth_topic, healthy=depth_ok),
            "imu": _topic_diag(topic=imu_topic, healthy=imu_ok),
            "raw_lidar": _topic_diag(topic=lidar_topic, healthy=lidar_ok is True),
            "left_image": _topic_diag(topic=stereo_left, healthy=stereo_left_ok),
            "right_image": _topic_diag(topic=stereo_right, healthy=stereo_right_ok),
            "visual_slam_odom": _topic_diag(topic=odom_topic, healthy=odom_ok),
            "local_odometry": _topic_diag(topic=odom_topic, healthy=odom_ok),
        },
    }


def _topics_present(
    entries: list[BridgeTopicMapping],
    live: set[str],
    publisher_counts: dict[str, int] | None = None,
) -> bool:
    if not entries or not all(entry.ros_topic_name in live for entry in entries):
        return False
    if not publisher_counts:
        return True
    return all(publisher_counts.get(entry.ros_topic_name, 0) > 0 for entry in entries)


def probe_bridge_topics(ros2_ws: Path) -> dict[str, Any]:
    """Compare live ROS/Gazebo topic graphs against warehouse_bridge.yaml."""
    ws = ros2_ws.resolve()
    mappings = load_bridge_config(ws)
    bridged = gz_to_ros_mappings(mappings)
    core_required = preflight_core_ros_topics(ws)
    ros_topics = list_ros2_topics_with_retry(ws, required_topics=core_required)
    publisher_probe_topics = (
        core_required
        | {"/clock", "/tf"}
        | {entry.ros_topic_name for entry in _preflight_lidar(bridged)}
    )
    publisher_counts = count_topic_publishers(ws, publisher_probe_topics)
    gz_topics, gz_error = list_gz_topics()

    missing_ros = sorted(m.ros_topic_name for m in bridged if m.ros_topic_name not in ros_topics)
    missing_gz = (
        sorted(m.gz_topic_name for m in bridged if m.gz_topic_name not in gz_topics)
        if gz_error is None
        else []
    )

    odom_entries = _preflight_odometry(bridged)
    rgbd_entries = _preflight_rgbd(bridged)
    imu_entries = _preflight_imu(bridged)
    lidar_entries = _preflight_lidar(bridged)
    stereo_left_entry, stereo_right_entry = _preflight_stereo_images(bridged)

    odom_topic = odom_entries[0].ros_topic_name if odom_entries else None
    odom_ready = _topics_present(odom_entries, ros_topics, publisher_counts)
    imu_ready = _topics_present(imu_entries, ros_topics, publisher_counts)
    rgbd_ready = _topics_present(rgbd_entries, ros_topics, publisher_counts)
    lidar_ready = _topics_present(lidar_entries, ros_topics, publisher_counts)
    stereo_left_ready = (
        stereo_left_entry is not None and stereo_left_entry.ros_topic_name in ros_topics
    )
    stereo_right_ready = (
        stereo_right_entry is not None and stereo_right_entry.ros_topic_name in ros_topics
    )

    rgb_topic = rgbd_entries[0].ros_topic_name if rgbd_entries else None
    depth_topic = next(
        (m.ros_topic_name for m in rgbd_entries if m.ros_topic_name.endswith("/depth_image")),
        None,
    )
    imu_topic = imu_entries[0].ros_topic_name if imu_entries else None
    lidar_topic = lidar_entries[0].ros_topic_name if lidar_entries else None
    stereo_left_topic = stereo_left_entry.ros_topic_name if stereo_left_entry else None
    stereo_right_topic = stereo_right_entry.ros_topic_name if stereo_right_entry else None
    rgbd_imu_ok = rgbd_ready and imu_ready
    lidar_required = _raw_lidar_required()
    lidar_status = lidar_ready if lidar_required or lidar_ready else None
    ros_graph_ok = bool(ros_topics)
    preflight_core_ready = odom_ready and rgbd_imu_ok

    payload = {
        "bridge_config_path": str(bridge_config_path(ws)),
        "odometry_topic": odom_topic,
        "rgb_topic": rgb_topic,
        "depth_topic": depth_topic,
        "imu_topic": imu_topic,
        "lidar_topic": lidar_topic,
        "stereo_left_topic": stereo_left_topic,
        "stereo_right_topic": stereo_right_topic,
        "listed_ros_topics": sorted(ros_topics),
        "ros_topics": sorted(ros_topics),
        "ros_topic_count": len(ros_topics),
        "configured_ros_topics": sorted(m.ros_topic_name for m in bridged),
        "missing_configured_ros_topics": missing_ros,
        "configured_gz_topics": sorted(m.gz_topic_name for m in bridged),
        "missing_configured_gz_topics": missing_gz,
        "gz_probe_error": gz_error,
        "ros_graph_healthy": ros_graph_ok,
        "local_position_ok": odom_ready,
        "odometry_healthy": odom_ready,
        "imu_healthy": imu_ready,
        "rgb_healthy": rgbd_ready,
        "depth_healthy": rgbd_ready,
        "lidar_healthy": lidar_status,
        "stereo_left_healthy": stereo_left_ready,
        "stereo_right_healthy": stereo_right_ready,
        "tf_ok": "/tf" in ros_topics or odom_ready,
        "slam_ready": odom_ready,
        "slam_tracking_ok": odom_ready,
        "source_transport_ok": bool(set(m.ros_topic_name for m in bridged) & ros_topics),
        "rgb_depth_imu_ok": rgbd_imu_ok,
        "lidar_ok": lidar_status,
        "sensors_ok": rgbd_imu_ok,
        "preflight_core_ready": preflight_core_ready,
        "perception_stable_for_ms": 8_000 if preflight_core_ready else 0,
        "perception_required_stable_ms": 8_000,
        "ros_domain_id": ros_domain_id(),
        "publisher_counts": publisher_counts,
        "clock_publishing": publisher_counts.get("/clock", 0) > 0,
    }
    payload["components"] = bridge_probe_to_components(payload)
    return payload


CRITICAL_PROBE_TOPICS: tuple[tuple[str, str], ...] = (
    ("odometry_topic", "Local odometry topic"),
    ("imu_topic", "IMU topic"),
    ("rgb_topic", "RGB camera topic"),
    ("depth_topic", "Depth camera topic"),
)


def missing_critical_topic_blockers(overlay: dict[str, Any]) -> list[str]:
    """Human-readable blockers for yaml-critical topics absent from the ROS graph."""
    if overlay.get("preflight_core_ready") is True:
        return []
    missing = set(overlay.get("missing_configured_ros_topics") or [])
    if not missing:
        publisher_counts = overlay.get("publisher_counts") or {}
        blockers = []
        for key, label in CRITICAL_PROBE_TOPICS:
            topic = overlay.get(key)
            if topic and publisher_counts.get(topic, 0) <= 0:
                blockers.append(f"{label} is present but has no publishers: {topic}")
        return blockers
    domain = str(overlay.get("ros_domain_id") or ros_domain_id())
    suffix = (
        f"(see warehouse_bridge.yaml; ROS_DOMAIN_ID={domain}). "
        "Ensure Gazebo and the bridge are running before preflight."
    )
    blockers: list[str] = []
    for key, label in CRITICAL_PROBE_TOPICS:
        topic = overlay.get(key)
        if topic and topic in missing:
            blockers.append(f"{label} missing from ROS graph: {topic} {suffix}")
    return blockers
