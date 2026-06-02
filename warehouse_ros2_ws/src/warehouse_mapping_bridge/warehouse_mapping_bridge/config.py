from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML optional at import
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class BridgeConfig:
    host: str
    port: int
    capture_root: Path
    profile: str
    ros_ws_url: str
    autolaunch: bool
    launch_cmd: str
    mavlink_vision_url: str
    odometry_state_path: Path


@dataclass(frozen=True)
class TopicRegistry:
    profile: str
    topics: dict[str, str]
    aliases: dict[str, list[str]]
    required_for_perception: tuple[str, ...]
    required_for_nvblox_any: tuple[str, ...]
    frames: dict[str, str]
    frame_aliases: dict[str, list[str]]


_ENV_OVERRIDES: dict[str, str] = {
    "rgb_image": "WAREHOUSE_RGB_TOPIC",
    "left_image": "WAREHOUSE_LEFT_IMAGE_TOPIC",
    "right_image": "WAREHOUSE_RIGHT_IMAGE_TOPIC",
    "depth": "WAREHOUSE_DEPTH_TOPIC",
    "imu": "WAREHOUSE_IMU_TOPIC",
    "visual_slam_odom": "WAREHOUSE_VISUAL_SLAM_ODOM_TOPIC",
    "local_odometry": "WAREHOUSE_LOCAL_ODOMETRY_TOPIC",
    "raw_lidar": "WAREHOUSE_RAW_LIDAR_TOPIC",
    "pointcloud": "WAREHOUSE_POINTCLOUD_TOPIC",
    "mesh": "WAREHOUSE_MESH_TOPIC",
    "mesh_marker": "WAREHOUSE_MESH_MARKER_TOPIC",
    "occupancy": "WAREHOUSE_OCCUPANCY_TOPIC",
    "esdf": "WAREHOUSE_ESDF_TOPIC",
    "static_map_slice": "WAREHOUSE_STATIC_MAP_SLICE_TOPIC",
    "combined_map_slice": "WAREHOUSE_COMBINED_MAP_SLICE_TOPIC",
    "back_projected_depth": "WAREHOUSE_BACK_PROJECTED_DEPTH_TOPIC",
    "health": "WAREHOUSE_MAPPING_HEALTH_TOPIC",
}

_DEFAULT_TOPICS_BY_PROFILE: dict[str, dict[str, str]] = {
    "gazebo": {
        "rgb_image": "/warehouse/front/rgbd/image",
        "left_image": "/warehouse/stereo/left/image",
        "right_image": "/warehouse/stereo/right/image",
        "depth": "/warehouse/front/rgbd/depth_image",
        "imu": "/imu",
        "visual_slam_odom": "/warehouse/drone/odometry",
        "local_odometry": "/warehouse/drone/odometry",
        "raw_lidar": "/warehouse/front/rgbd/points",
        "pointcloud": "/nvblox_node/static_esdf_pointcloud",
        "mesh": "/nvblox_node/mesh",
        "occupancy": "/nvblox_node/occupancy_layer",
        "esdf": "/nvblox_node/static_esdf_pointcloud",
        "static_map_slice": "/nvblox_node/static_map_slice",
        "combined_map_slice": "/nvblox_node/combined_map_slice",
        "health": "/warehouse/mapping/health",
    },
    "isaac_ros_nvblox_stereo": {
        "rgb_image": "/warehouse/front/rgbd/image",
        "left_image": "/warehouse/stereo/left/image",
        "right_image": "/warehouse/stereo/right/image",
        "depth": "/warehouse/front/rgbd/depth_image",
        "imu": "/imu",
        "visual_slam_odom": "/visual_slam/tracking/odometry",
        "local_odometry": "/warehouse/local_odometry",
        "raw_lidar": "/scan",
        "pointcloud": "/nvblox_node/static_esdf_pointcloud",
        "mesh": "/nvblox_node/mesh",
        "occupancy": "/nvblox_node/occupancy_layer",
        "esdf": "/nvblox_node/static_esdf_pointcloud",
        "static_map_slice": "/nvblox_node/static_map_slice",
        "combined_map_slice": "/nvblox_node/combined_map_slice",
        "health": "/warehouse/mapping/health",
    },
}

_DEFAULT_REQUIRED_FOR_PERCEPTION: tuple[str, ...] = (
    "rgb_image",
    "depth",
    "imu",
    "raw_lidar",
    "visual_slam_odom",
)

_DEFAULT_REQUIRED_FOR_NVBLOX_ANY: tuple[str, ...] = (
    "mesh",
    "pointcloud",
    "occupancy",
    "esdf",
    "static_map_slice",
    "combined_map_slice",
)


def int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _topics_yaml_path() -> Path:
    override = os.getenv("WAREHOUSE_TOPIC_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    here = Path(__file__).resolve().parent
    share = os.getenv("WAREHOUSE_MAPPING_BRIDGE_SHARE", "").strip()
    candidates = [
        here / "warehouse_topics.yaml",
        here.parent / "config" / "warehouse_topics.yaml",
    ]
    if share:
        candidates.insert(0, Path(share) / "config" / "warehouse_topics.yaml")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def _default_topic_profile() -> str:
    explicit = os.getenv("WAREHOUSE_TOPIC_PROFILE", "").strip()
    if explicit:
        return explicit
    if bool_env("WAREHOUSE_GAZEBO_SIM"):
        return "gazebo"
    return os.getenv("WAREHOUSE_ROS_PROFILE", "isaac_ros_nvblox_stereo")


def _load_yaml_registry() -> dict[str, object]:
    path = _topics_yaml_path()
    if yaml is None or not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def discover_gz_imu_topic() -> str | None:
    """Return the first IMU-like Gazebo topic from the running sim, if explicitly enabled."""
    if not bool_env("WAREHOUSE_GAZEBO_IMU_AUTO_DISCOVER", False):
        return None
    if not shutil.which("gz"):
        return None

    env = os.environ.copy()
    partition = os.getenv("GZ_PARTITION", "").strip()
    if partition:
        env["GZ_PARTITION"] = partition

    timeout_s = max(0.25, float_env("WAREHOUSE_GZ_TOPIC_LIST_TIMEOUT_S", 1.0))

    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    for line in result.stdout.splitlines():
        topic = line.strip()
        if topic.startswith("/") and "imu" in topic.lower():
            return topic
    return None


@lru_cache(maxsize=1)
def topic_registry() -> TopicRegistry:
    payload = _load_yaml_registry()
    profile = _default_topic_profile()
    profiles = payload.get("profiles", {})
    profile_topics = profiles.get(profile, {})
    if not isinstance(profile_topics, dict):
        profile_topics = {}
    if not profile_topics and profile != "gazebo":
        profile_topics = profiles.get("gazebo", {})
    if not isinstance(profile_topics, dict):
        profile_topics = {}

    default_topics = dict(
        _DEFAULT_TOPICS_BY_PROFILE.get(
            profile,
            _DEFAULT_TOPICS_BY_PROFILE["gazebo"],
        )
    )

    topics: dict[str, str] = default_topics | {
        str(k): str(v)
        for k, v in profile_topics.items()
        if v is not None and str(v).strip()
    }
    aliases_raw = payload.get("aliases", {})
    aliases: dict[str, list[str]] = {}
    if isinstance(aliases_raw, dict):
        for key, values in aliases_raw.items():
            if isinstance(values, list):
                aliases[str(key)] = [str(item) for item in values]

    for key, env_name in _ENV_OVERRIDES.items():
        raw = os.getenv(env_name, "").strip()
        if raw:
            topics[key] = raw

    odom_topic = os.getenv("WAREHOUSE_ODOMETRY_TOPIC", "").strip()
    if odom_topic:
        topics["visual_slam_odom"] = odom_topic
        if not os.getenv("WAREHOUSE_LOCAL_ODOMETRY_TOPIC", "").strip():
            topics["local_odometry"] = odom_topic

    gz_imu = os.getenv("WAREHOUSE_GAZEBO_IMU_TOPIC", "").strip()
    if gz_imu:
        topics["imu"] = gz_imu
    elif profile == "gazebo" and not str(topics.get("imu", "")).strip():
        discovered = discover_gz_imu_topic()
        if discovered:
            topics["imu"] = discovered

    rgb_topic = topics.get("rgb_image", "/warehouse/front/rgbd/image")
    topics.setdefault("rgb_image_compressed", f"{rgb_topic}/compressed")
    depth_topic = topics.get("depth", "/warehouse/front/rgbd/depth_image")
    topics.setdefault("depth_compressed", f"{depth_topic}/compressed")
    left_topic = topics.get("left_image", "/warehouse/stereo/left/image")
    topics.setdefault("left_image_compressed", f"{left_topic}/compressed")
    right_topic = topics.get("right_image", "/warehouse/stereo/right/image")
    topics.setdefault("right_image_compressed", f"{right_topic}/compressed")
    topics.setdefault("health", "/warehouse/mapping/health")

    required = payload.get("required_for_perception", list(_DEFAULT_REQUIRED_FOR_PERCEPTION))
    nvblox_required = payload.get("required_for_nvblox_any", list(_DEFAULT_REQUIRED_FOR_NVBLOX_ANY))
    frames_raw = payload.get("frames", {})
    frame_aliases_raw = payload.get("frame_aliases", {})
    frame_aliases: dict[str, list[str]] = {}
    if isinstance(frame_aliases_raw, dict):
        for key, values in frame_aliases_raw.items():
            if isinstance(values, list):
                frame_aliases[str(key)] = [str(item) for item in values]
    frames = {
        "odom": os.getenv("WAREHOUSE_ODOM_FRAME", "odom"),
        "base_link": os.getenv("WAREHOUSE_BASE_LINK_FRAME", "base_link"),
        "camera": os.getenv("WAREHOUSE_RGBD_FRAME", "front_rgbd_camera_link"),
    }
    if isinstance(frames_raw, dict):
        for key in ("odom", "base_link", "camera"):
            if frames_raw.get(key):
                frames[key] = str(frames_raw[key])
    if profile == "gazebo":
        gazebo_frames = payload.get("gazebo_frames", {})
        if isinstance(gazebo_frames, dict):
            for key in ("odom", "base_link", "camera"):
                if gazebo_frames.get(key):
                    frames[key] = str(gazebo_frames[key])

    required_tuple = (
        tuple(str(x) for x in required)
        if isinstance(required, list)
        else _DEFAULT_REQUIRED_FOR_PERCEPTION
    )
    if profile == "gazebo":
        require_local = os.getenv("WAREHOUSE_REQUIRE_LOCAL_ODOMETRY", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not require_local:
            required_tuple = tuple(key for key in required_tuple if key != "local_odometry")
        require_lidar = os.getenv("WAREHOUSE_REQUIRE_RAW_LIDAR", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not require_lidar:
            required_tuple = tuple(key for key in required_tuple if key != "raw_lidar")
        if not os.getenv("WAREHOUSE_LOCAL_ODOMETRY_TOPIC", "").strip():
            topics["local_odometry"] = topics.get(
                "visual_slam_odom",
                topics.get("local_odometry", "/warehouse/drone/odometry"),
            )
    nvblox_required_tuple = (
        tuple(str(x) for x in nvblox_required)
        if isinstance(nvblox_required, list)
        else _DEFAULT_REQUIRED_FOR_NVBLOX_ANY
    )

    return TopicRegistry(
        profile=profile,
        topics=topics,
        aliases=aliases,
        required_for_perception=required_tuple,
        required_for_nvblox_any=nvblox_required_tuple,
        frames=frames,
        frame_aliases=frame_aliases,
    )


def load_config() -> BridgeConfig:
    capture_root = Path(
        os.getenv("WAREHOUSE_ROS_CAPTURE_ROOT", "/backend/storage/warehouse_ros")
    ).expanduser()
    profile = os.getenv("WAREHOUSE_ROS_PROFILE", "").strip() or _default_topic_profile()
    return BridgeConfig(
        host=os.getenv("WAREHOUSE_ROS_BRIDGE_HOST", "0.0.0.0"),
        port=int_env("WAREHOUSE_ROS_BRIDGE_PORT", 8088),
        capture_root=capture_root.resolve(),
        profile=profile,
        ros_ws_url=os.getenv("WAREHOUSE_ROS_WS_URL", ""),
        autolaunch=bool_env("WAREHOUSE_ROS_AUTOLAUNCH", False),
        launch_cmd=os.getenv(
            "WAREHOUSE_ROS_LAUNCH_CMD",
            "ros2 launch warehouse_mapping_bridge isaac_warehouse_mapping.launch.py",
        ),
        mavlink_vision_url=os.getenv("WAREHOUSE_MAVLINK_VISION_URL", "udpout:127.0.0.1:14550"),
        odometry_state_path=Path(
            os.getenv(
                "WAREHOUSE_ODOMETRY_STATE_PATH",
                str(capture_root / "latest_odometry.json"),
            )
        ).expanduser(),
    )


def topic_env() -> dict[str, str]:
    return dict(topic_registry().topics)


def topic_aliases() -> dict[str, list[str]]:
    return dict(topic_registry().aliases)
