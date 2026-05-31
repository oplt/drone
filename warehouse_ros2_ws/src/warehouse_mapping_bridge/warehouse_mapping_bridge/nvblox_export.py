from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from time import monotonic

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def export_on_stop_enabled() -> bool:
    return _bool_env("WAREHOUSE_NVBLOX_EXPORT_ON_STOP", True)


def record_snapshot_on_stop_enabled(*, profile: str) -> bool:
    if os.getenv("WAREHOUSE_RECORD_SNAPSHOT_ON_STOP") is not None:
        return _bool_env("WAREHOUSE_RECORD_SNAPSHOT_ON_STOP", False)
    return profile == "gazebo"


def nvblox_node_active(listed_topics: set[str] | None) -> bool:
    if not listed_topics:
        return False
    prefix = os.getenv("WAREHOUSE_NVBLOX_TOPIC_PREFIX", "/nvblox_node/")
    return any(topic.startswith(prefix) for topic in listed_topics)


def _wait_for_file(path: Path, *, timeout_s: float) -> bool:
    deadline = monotonic() + max(0.5, timeout_s)
    while monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return True
        time.sleep(0.25)
    return path.is_file() and path.stat().st_size > 0


def call_filepath_service(service_name: str, file_path: Path, *, timeout_s: float = 30.0) -> bool:
    if not shutil.which("ros2"):
        return False
    file_path.parent.mkdir(parents=True, exist_ok=True)
    request = f'{{file_path: "{file_path.as_posix()}"}}'
    try:
        result = subprocess.run(
            [
                "ros2",
                "service",
                "call",
                service_name,
                "nvblox_msgs/srv/FilePath",
                request,
            ],
            timeout=timeout_s,
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("nvblox service call failed service=%s error=%s", service_name, exc)
        return False
    if result.returncode != 0:
        logger.warning(
            "nvblox service call failed service=%s rc=%s stderr=%s",
            service_name,
            result.returncode,
            (result.stderr or "").strip(),
        )
        return False
    return True


def export_nvblox_artifacts(
    session_dir: Path,
    *,
    listed_topics: set[str] | None,
    profile: str,
) -> int:
    """Persist nvblox mesh/map files and optional rosbag snapshot into session artifacts."""
    if not export_on_stop_enabled():
        return 0
    if not nvblox_node_active(listed_topics):
        logger.info("Skipping nvblox export — nvblox topics not present in ROS graph")
        return 0

    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    exported = 0
    wait_s = float(os.getenv("WAREHOUSE_NVBLOX_EXPORT_WAIT_S", "20"))

    mesh_path = artifacts_dir / "mesh.ply"
    if call_filepath_service("/nvblox_node/save_ply", mesh_path):
        if _wait_for_file(mesh_path, timeout_s=wait_s):
            exported += 1
            logger.info("Exported nvblox mesh to %s", mesh_path)
        else:
            logger.warning("nvblox save_ply did not produce %s within %.0fs", mesh_path, wait_s)

    map_path = artifacts_dir / "nvblox_map.bin"
    if call_filepath_service("/nvblox_node/save_map", map_path):
        if _wait_for_file(map_path, timeout_s=wait_s):
            exported += 1
            logger.info("Exported nvblox map to %s", map_path)
        else:
            logger.warning("nvblox save_map did not produce %s within %.0fs", map_path, wait_s)

    if exported == 0 and record_snapshot_on_stop_enabled(profile=profile):
        exported += record_mapping_snapshot(
            session_dir,
            listed_topics=listed_topics,
        )
    return exported


def record_mapping_snapshot(
    session_dir: Path,
    *,
    listed_topics: set[str] | None,
) -> int:
    from .config import topic_env

    if not listed_topics:
        return 0
    topics = topic_env()
    record_topics: list[str] = []
    for key in ("pointcloud", "esdf", "mesh", "depth", "raw_lidar", "visual_slam_odom"):
        topic = (topics.get(key) or "").strip()
        if topic and topic in listed_topics and topic not in record_topics:
            record_topics.append(topic)
    if not record_topics:
        return 0

    duration_s = max(1, int(os.getenv("WAREHOUSE_RECORD_SNAPSHOT_DURATION_S", "5")))
    bag_path = session_dir / "artifacts" / "mapping_snapshot"
    if bag_path.exists():
        shutil.rmtree(bag_path, ignore_errors=True)

    cmd = [
        "ros2",
        "bag",
        "record",
        "-o",
        str(bag_path),
        "--duration",
        str(duration_s),
        *record_topics,
    ]
    try:
        result = subprocess.run(
            cmd,
            timeout=duration_s + 10,
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("Warehouse mapping rosbag snapshot failed: %s", exc)
        return 0
    if result.returncode != 0:
        logger.warning(
            "Warehouse mapping rosbag snapshot failed stderr=%s",
            (result.stderr or "").strip(),
        )
        return 0
    if bag_path.exists():
        logger.info(
            "Recorded warehouse mapping snapshot bag topics=%s path=%s",
            record_topics,
            bag_path,
        )
        return 1
    return 0
