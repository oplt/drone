from __future__ import annotations

import os
import shlex

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, TextSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


_OPTIONAL_DEVICE_COMMANDS = (
    "WAREHOUSE_REAL_CAMERA_LAUNCH_CMD",
    "WAREHOUSE_REAL_IMU_LAUNCH_CMD",
    "WAREHOUSE_REAL_LIDAR_LAUNCH_CMD",
    "WAREHOUSE_REAL_VSLAM_LAUNCH_CMD",
    "WAREHOUSE_REAL_DEPTH_LAUNCH_CMD",
    "WAREHOUSE_NVBLOX_LAUNCH_CMD",
)


def _process_from_env(name: str) -> ExecuteProcess | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    cmd = shlex.split(raw)
    if not cmd:
        return None
    return ExecuteProcess(cmd=cmd, output="screen", name=name)


def _helper_node(executable: str, name: str) -> Node:
    default_params = PathJoinSubstitution(
        [FindPackageShare("warehouse_mapping_bridge"), "config", "defaults_real_device.yaml"]
    )
    return Node(
        package="warehouse_mapping_bridge",
        executable=executable,
        name=name,
        output="screen",
        parameters=[default_params, {"use_sim_time": LaunchConfiguration("use_sim_time")}],
    )


def generate_launch_description() -> LaunchDescription:
    actions = [
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("rosbridge_port", default_value="9090"),
        SetEnvironmentVariable("WAREHOUSE_BRIDGE_FLOW", "real_device"),
        SetEnvironmentVariable("WAREHOUSE_GAZEBO_SIM", "0"),
        SetEnvironmentVariable("WAREHOUSE_TOPIC_PROFILE", "real_device"),
        SetEnvironmentVariable("WAREHOUSE_ROS_PROFILE", "real_device"),
    ]

    for env_name in _OPTIONAL_DEVICE_COMMANDS:
        process = _process_from_env(env_name)
        if process is not None:
            actions.append(process)

    actions.extend(
        [
            _helper_node("warehouse_topic_adapter", "warehouse_topic_adapter"),
            _helper_node("warehouse_bridge_service", "warehouse_bridge_service"),
            _helper_node("warehouse_sim_tf_broadcaster", "warehouse_real_tf_broadcaster"),
            _helper_node("warehouse_odometry_export", "warehouse_odometry_export"),
            _helper_node("warehouse_health_monitor", "warehouse_health_monitor"),
            _helper_node("warehouse_artifact_exporter", "warehouse_artifact_exporter"),
            _helper_node("warehouse_live_map_publisher", "warehouse_live_map_publisher"),
            _helper_node("warehouse_diagnostics_aggregator", "warehouse_diagnostics_aggregator"),
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "launch",
                    "rosbridge_server",
                    "rosbridge_websocket_launch.xml",
                    [TextSubstitution(text="port:="), LaunchConfiguration("rosbridge_port")],
                ],
                output="screen",
                name="rosbridge_websocket",
            ),
        ]
    )
    return LaunchDescription(actions)
