from __future__ import annotations

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            Node(
                package="warehouse_mapping_bridge",
                executable="warehouse_bridge_service",
                name="warehouse_bridge_service",
                output="screen",
            )
        ]
    )

