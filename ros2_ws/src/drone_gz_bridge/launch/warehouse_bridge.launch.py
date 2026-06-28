import hashlib
import json
import math
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


REQUIRED_EDGES = {
    ("base_link", "lidar_link"),
    ("base_link", "camera_link"),
    ("camera_link", "camera_optical_frame"),
    ("base_link", "imu_link"),
    ("base_link", "rgbd_link"),
}


def _load_calibration(path: Path):
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    transforms = payload.get("transforms") if isinstance(payload, dict) else None
    if not isinstance(transforms, list):
        raise RuntimeError("sensor_extrinsics.yaml has no transforms list")
    edges = {(item.get("parent_frame"), item.get("child_frame")) for item in transforms}
    children = [item.get("child_frame") for item in transforms]
    if edges != REQUIRED_EDGES or len(children) != len(set(children)):
        raise RuntimeError("sensor extrinsics must define the exact stable frame tree once")
    for item in transforms:
        rotation = item.get("rotation", {})
        norm = math.sqrt(sum(float(rotation.get(axis, 0.0)) ** 2 for axis in "xyzw"))
        if abs(norm - 1.0) > 1e-3:
            raise RuntimeError(f"non-unit quaternion for {item.get('child_frame')}")
    transforms.sort(key=lambda item: (item["parent_frame"], item["child_frame"]))
    canonical = json.dumps(
        {"schema_version": 1, "transforms": transforms},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return transforms, hashlib.sha256(canonical).hexdigest()


def _static_tf_node(item):
    translation = item["translation"]
    rotation = item["rotation"]
    child = item["child_frame"]
    return Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name=f"calibration_{child}_tf",
        output="screen",
        arguments=[
            "--x", str(translation["x"]), "--y", str(translation["y"]),
            "--z", str(translation["z"]), "--qx", str(rotation["x"]),
            "--qy", str(rotation["y"]), "--qz", str(rotation["z"]),
            "--qw", str(rotation["w"]), "--frame-id", item["parent_frame"],
            "--child-frame-id", child,
        ],
        parameters=[{"use_sim_time": True}],
    )


def _gazebo_sensor_alias_node(name, parent, child):
    return Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name=name,
        output="screen",
        arguments=[
            "--x", "0", "--y", "0", "--z", "0",
            "--qx", "0", "--qy", "0", "--qz", "0", "--qw", "1",
            "--frame-id", parent, "--child-frame-id", child,
        ],
        parameters=[{"use_sim_time": True}],
    )


def generate_launch_description():
    pkg_share = Path(get_package_share_directory("drone_gz_bridge"))
    bridge_config = pkg_share / "config" / "warehouse_bridge.yaml"
    calibration_file = pkg_share / "config" / "sensor_extrinsics.yaml"
    transforms, checksum = _load_calibration(calibration_file)
    return LaunchDescription([
        DeclareLaunchArgument("warehouse_map_x", default_value="0.0"),
        DeclareLaunchArgument("warehouse_map_y", default_value="0.0"),
        DeclareLaunchArgument("warehouse_map_z", default_value="0.0"),
        DeclareLaunchArgument("warehouse_map_qx", default_value="0.0"),
        DeclareLaunchArgument("warehouse_map_qy", default_value="0.0"),
        DeclareLaunchArgument("warehouse_map_qz", default_value="0.0"),
        DeclareLaunchArgument("warehouse_map_qw", default_value="1.0"),
        DeclareLaunchArgument("enable_slam_localization_bridge", default_value="false"),
        Node(
            package="drone_gz_bridge",
            executable="map_to_odom_tf",
            name="warehouse_map_to_odom_tf",
            output="screen",
            parameters=[{
                "use_sim_time": True,
                "translation_x": LaunchConfiguration("warehouse_map_x"),
                "translation_y": LaunchConfiguration("warehouse_map_y"),
                "translation_z": LaunchConfiguration("warehouse_map_z"),
                "rotation_x": LaunchConfiguration("warehouse_map_qx"),
                "rotation_y": LaunchConfiguration("warehouse_map_qy"),
                "rotation_z": LaunchConfiguration("warehouse_map_qz"),
                "rotation_w": LaunchConfiguration("warehouse_map_qw"),
            }],
        ),
        Node(
            package="ros_gz_bridge", executable="parameter_bridge",
            name="warehouse_gz_bridge", output="screen",
            parameters=[{"config_file": str(bridge_config), "use_sim_time": True}],
        ),
        Node(
            package="drone_gz_bridge", executable="odom_to_tf",
            name="warehouse_odom_to_tf", output="screen",
            parameters=[{
                "use_sim_time": True, "odom_topic": "/warehouse/drone/odometry",
                "parent_frame_override": "odom", "child_frame_override": "base_link",
                "sensor_calibration_checksum": checksum,
            }],
        ),
        *[_static_tf_node(item) for item in transforms],
        _gazebo_sensor_alias_node(
            "gazebo_mid360_frame_alias",
            "lidar_link",
            "iris_rplidar_rgbd/mid360_lidar_link/mid360_lidar",
        ),
        _gazebo_sensor_alias_node(
            "gazebo_rgbd_frame_alias",
            "rgbd_link",
            "iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera",
        ),
        Node(
            package="drone_gz_bridge", executable="gimbal_to_tf",
            name="warehouse_gimbal_to_tf", output="screen",
            parameters=[{"use_sim_time": True, "joint_state_topic": "/joint_states"}],
        ),
        Node(
            package="drone_gz_bridge", executable="calibration_guard",
            name="warehouse_sensor_calibration_guard", output="screen",
            parameters=[{
                "use_sim_time": True, "calibration_file": str(calibration_file),
                "expected_checksum": checksum,
            }],
        ),
        Node(
            package="drone_gz_bridge",
            executable="slam_localization_bridge",
            name="warehouse_slam_localization_bridge",
            output="screen",
            condition=IfCondition(LaunchConfiguration("enable_slam_localization_bridge")),
            parameters=[{"use_sim_time": True}],
        ),
    ])
