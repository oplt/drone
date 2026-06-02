from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument("profile", default_value="isaac_ros_nvblox_stereo"),
            DeclareLaunchArgument("capture_root", default_value="/backend/storage/warehouse_ros"),
            DeclareLaunchArgument("host", default_value="0.0.0.0"),
            DeclareLaunchArgument("port", default_value="8088"),
            SetEnvironmentVariable("WAREHOUSE_ROS_PROFILE", LaunchConfiguration("profile")),
            SetEnvironmentVariable("WAREHOUSE_TOPIC_PROFILE", LaunchConfiguration("profile")),
            SetEnvironmentVariable("WAREHOUSE_ROS_CAPTURE_ROOT", LaunchConfiguration("capture_root")),
            SetEnvironmentVariable("WAREHOUSE_ROS_BRIDGE_HOST", LaunchConfiguration("host")),
            SetEnvironmentVariable("WAREHOUSE_ROS_BRIDGE_PORT", LaunchConfiguration("port")),
            Node(
                package="warehouse_mapping_bridge",
                executable="warehouse_bridge_service",
                name="warehouse_bridge_service",
                output="screen",
            ),
        ]
    )
