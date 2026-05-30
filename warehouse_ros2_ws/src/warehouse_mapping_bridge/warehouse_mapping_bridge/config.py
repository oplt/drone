from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> BridgeConfig:
    capture_root = Path(
        os.getenv("WAREHOUSE_ROS_CAPTURE_ROOT", "/data/warehouse_ros")
    ).expanduser()
    return BridgeConfig(
        host=os.getenv("WAREHOUSE_ROS_BRIDGE_HOST", "0.0.0.0"),
        port=int(os.getenv("WAREHOUSE_ROS_BRIDGE_PORT", "8088")),
        capture_root=capture_root.resolve(),
        profile=os.getenv("WAREHOUSE_ROS_PROFILE", "isaac_ros_nvblox_stereo"),
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
    rgb_topic = os.getenv("WAREHOUSE_RGB_TOPIC", "/warehouse/front/rgbd/image")
    return {
        "rgb_image": rgb_topic,
        "rgb_image_compressed": os.getenv(
            "WAREHOUSE_RGB_COMPRESSED_TOPIC",
            f"{rgb_topic}/compressed",
        ),
        "left_image": os.getenv("WAREHOUSE_LEFT_IMAGE_TOPIC", "/left/image_rect"),
        "left_image_compressed": os.getenv(
            "WAREHOUSE_LEFT_IMAGE_COMPRESSED_TOPIC",
            f"{os.getenv('WAREHOUSE_LEFT_IMAGE_TOPIC', '/left/image_rect')}/compressed",
        ),
        "right_image": os.getenv("WAREHOUSE_RIGHT_IMAGE_TOPIC", "/right/image_rect"),
        "right_image_compressed": os.getenv(
            "WAREHOUSE_RIGHT_IMAGE_COMPRESSED_TOPIC",
            f"{os.getenv('WAREHOUSE_RIGHT_IMAGE_TOPIC', '/right/image_rect')}/compressed",
        ),
        "imu": os.getenv("WAREHOUSE_IMU_TOPIC", "/imu"),
        "visual_slam_odom": os.getenv(
            "WAREHOUSE_VISUAL_SLAM_ODOM_TOPIC",
            "/visual_slam/tracking/odometry",
        ),
        "local_odometry": os.getenv("WAREHOUSE_LOCAL_ODOMETRY_TOPIC", "/warehouse/local_odometry"),
        "depth": os.getenv("WAREHOUSE_DEPTH_TOPIC", "/depth"),
        "depth_compressed": os.getenv(
            "WAREHOUSE_DEPTH_COMPRESSED_TOPIC",
            f"{os.getenv('WAREHOUSE_DEPTH_TOPIC', '/depth')}/compressed",
        ),
        "raw_lidar": os.getenv("WAREHOUSE_RAW_LIDAR_TOPIC", "/lidar/points"),
        "pointcloud": os.getenv("WAREHOUSE_POINTCLOUD_TOPIC", "/nvblox_node/pointcloud"),
        "mesh": os.getenv("WAREHOUSE_MESH_TOPIC", "/nvblox_node/mesh"),
        "mesh_marker": os.getenv("WAREHOUSE_MESH_MARKER_TOPIC", "/nvblox_node/mesh_marker"),
        "occupancy": os.getenv("WAREHOUSE_OCCUPANCY_TOPIC", "/nvblox_node/occupancy_layer"),
        "esdf": os.getenv("WAREHOUSE_ESDF_TOPIC", "/nvblox_node/static_esdf_pointcloud"),
        "back_projected_depth": os.getenv(
            "WAREHOUSE_BACK_PROJECTED_DEPTH_TOPIC",
            "/nvblox_node/back_projected_depth",
        ),
        "health": os.getenv("WAREHOUSE_MAPPING_HEALTH_TOPIC", "/warehouse/mapping/health"),
    }
