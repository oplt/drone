from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def require_ros2():
    try:
        import rclpy  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 dependencies are not installed in this environment. "
            "Source your ROS 2 workspace and install rclpy/sensor_msgs/std_msgs first."
        ) from exc


def api_base_url() -> str:
    return os.getenv("IRRIGATION_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def api_headers() -> dict[str, str]:
    token = os.getenv("IRRIGATION_API_TOKEN", "").strip()
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def mission_id() -> str:
    return os.getenv("IRRIGATION_ACTIVE_MISSION_ID", "").strip()


def mission_spool_root() -> Path:
    root = Path(os.getenv("IRRIGATION_ROS2_CACHE_DIR", "backend/storage/irrigation_ros2")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def discover_gazebo_image_topics() -> list[str]:
    if shutil.which("gz") is None:
        return []
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            capture_output=True,
            text=True,
            timeout=4.0,
            check=True,
        )
    except Exception:
        return []

    candidates: list[str] = []
    for line in result.stdout.splitlines():
        topic = line.strip()
        if not topic:
            continue
        topic_lower = topic.lower()
        if "image" not in topic_lower:
            continue
        if "camera" not in topic_lower and "sensor" not in topic_lower:
            continue
        candidates.append(topic)
    return candidates


def choose_gazebo_camera_topic() -> str | None:
    explicit = os.getenv("IRRIGATION_GAZEBO_CAMERA_TOPIC", "").strip()
    if explicit:
        return explicit
    topics = discover_gazebo_image_topics()
    if not topics:
        return None
    preferred_tokens = ("iris", "camera", "image", "sensor")
    topics.sort(
        key=lambda topic: (
            0 if "iris" in topic.lower() else 1,
            sum(1 for token in preferred_tokens if token in topic.lower()),
            -len(topic),
        ),
        reverse=True,
    )
    return topics[0]


def ros_camera_input_topic() -> str:
    explicit = os.getenv("IRRIGATION_ROS_CAMERA_INPUT_TOPIC", "").strip()
    if explicit:
        return explicit
    discovered = choose_gazebo_camera_topic()
    if discovered:
        return discovered
    return "/world/default/model/iris_with_camera/link/camera_link/sensor/camera/image"


def json_message(data: dict[str, Any]):
    from std_msgs.msg import String

    message = String()
    message.data = json.dumps(data, sort_keys=True)
    return message


def post_capture(*, mission_id: str, payload: dict[str, Any], image_path: Path) -> dict[str, Any]:
    with image_path.open("rb") as image_file:
        response = requests.post(
            f"{api_base_url()}/irrigation/captures",
            data={
                "mission_id": mission_id,
                "timestamp_utc": payload["timestamp_utc"],
                "lat": str(payload["lat"]),
                "lon": str(payload["lon"]),
                "alt_m": "" if payload.get("alt_m") is None else str(payload["alt_m"]),
                "yaw_deg": "" if payload.get("yaw_deg") is None else str(payload["yaw_deg"]),
                "pitch_deg": "" if payload.get("pitch_deg") is None else str(payload["pitch_deg"]),
                "roll_deg": "" if payload.get("roll_deg") is None else str(payload["roll_deg"]),
                "waypoint_seq": ""
                if payload.get("waypoint_seq") is None
                else str(payload["waypoint_seq"]),
                "meta_data": json.dumps(payload.get("meta_data", {})),
            },
            files={"image": (image_path.name, image_file, "image/jpeg")},
            headers=api_headers(),
            timeout=30,
        )
    response.raise_for_status()
    return response.json()


def post_process(mission_id_value: str) -> dict[str, Any]:
    response = requests.post(
        f"{api_base_url()}/irrigation/missions/{mission_id_value}/process",
        headers=api_headers(),
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def get_mission_runtime(mission_id_value: str) -> dict[str, Any]:
    response = requests.get(
        f"{api_base_url()}/tasks/missions/{mission_id_value}",
        headers=api_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_ops_health() -> dict[str, Any]:
    response = requests.get(
        f"{api_base_url()}/telemetry/ops-health",
        headers=api_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@dataclass(frozen=True)
class DroneStateSample:
    timestamp_sec: float
    lat: float
    lon: float
    alt_m: float | None
    yaw_deg: float | None
    pitch_deg: float | None
    roll_deg: float | None
    waypoint_seq: int | None
    mission_id: str | None = None


def active_mission_id() -> str | None:
    explicit = mission_id()
    if explicit:
        return explicit
    try:
        payload = get_ops_health()
    except Exception:
        return None
    active_mission = payload.get("active_mission") or {}
    mission_id_value = active_mission.get("flight_id")
    if isinstance(mission_id_value, str) and mission_id_value.strip():
        return mission_id_value.strip()
    return None
