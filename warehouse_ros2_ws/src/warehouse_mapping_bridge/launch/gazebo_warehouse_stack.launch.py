# launch/gazebo_warehouse_stack.launch.py
from __future__ import annotations

from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            Node(
                package="warehouse_mapping_bridge",
                executable="warehouse_bridge_service",
                name="warehouse_bridge_service",
                output="screen",
            ),
            Node(
                package="warehouse_mapping_bridge",
                executable="warehouse_sim_tf_broadcaster",
                name="warehouse_sim_tf_broadcaster",
                output="screen",
            ),
            Node(
                package="warehouse_mapping_bridge",
                executable="warehouse_odometry_export",
                name="warehouse_odometry_export",
                output="screen",
            ),
            Node(
                package="warehouse_mapping_bridge",
                executable="warehouse_health_monitor",
                name="warehouse_health_monitor",
                output="screen",
            ),
            Node(
                package="warehouse_mapping_bridge",
                executable="warehouse_vision_mavlink_bridge",
                name="warehouse_vision_mavlink_bridge",
                output="screen",
            ),
            Node(
                package="warehouse_mapping_bridge",
                executable="warehouse_artifact_exporter",
                name="warehouse_artifact_exporter",
                output="screen",
            ),
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "launch",
                    "rosbridge_server",
                    "rosbridge_websocket_launch.xml",
                    "port:=9090",
                ],
                output="screen",
                name="rosbridge_websocket",
            ),
        ]
    )