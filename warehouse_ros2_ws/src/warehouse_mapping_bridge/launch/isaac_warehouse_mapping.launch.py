from __future__ import annotations

import os
import shlex

from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def _process_from_env(name: str) -> ExecuteProcess | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    cmd = shlex.split(raw)
    if not cmd:
        return None
    return ExecuteProcess(cmd=cmd, output="screen", name=name)


def generate_launch_description() -> LaunchDescription:
    actions = []

    for env_name in (
        "WAREHOUSE_CAMERA_LAUNCH_CMD",
        "WAREHOUSE_IMU_LAUNCH_CMD",
        "WAREHOUSE_IMAGE_PIPELINE_LAUNCH_CMD",
        "WAREHOUSE_VISUAL_SLAM_LAUNCH_CMD",
        "WAREHOUSE_DEPTH_LAUNCH_CMD",
        "WAREHOUSE_NVBLOX_LAUNCH_CMD",
        "WAREHOUSE_RVIZ_LAUNCH_CMD",
    ):
        process = _process_from_env(env_name)
        if process is not None:
            actions.append(process)

    actions.extend(
        [
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
        ]
    )
    return LaunchDescription(actions)
