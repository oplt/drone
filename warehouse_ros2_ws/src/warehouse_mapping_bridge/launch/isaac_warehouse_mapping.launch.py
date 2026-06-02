from __future__ import annotations

import os
import shlex

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


_REQUIRED_STACK_COMMANDS = (
    "WAREHOUSE_CAMERA_LAUNCH_CMD",
    "WAREHOUSE_IMU_LAUNCH_CMD",
    "WAREHOUSE_IMAGE_PIPELINE_LAUNCH_CMD",
    "WAREHOUSE_VISUAL_SLAM_LAUNCH_CMD",
    "WAREHOUSE_DEPTH_LAUNCH_CMD",
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


def _validate_required_commands(_context, *_args, **_kwargs) -> list[ExecuteProcess]:
    if os.getenv("WAREHOUSE_ALLOW_PARTIAL_ISAAC_LAUNCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return []
    missing = [name for name in _REQUIRED_STACK_COMMANDS if not os.getenv(name, "").strip()]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            "Isaac warehouse launch requires full stack commands. "
            f"Missing: {joined}. Set WAREHOUSE_ALLOW_PARTIAL_ISAAC_LAUNCH=1 for helper-only launch."
        )
    return []


def _helper_node(executable: str, name: str) -> Node:
    default_params = PathJoinSubstitution(
        [FindPackageShare("warehouse_mapping_bridge"), "config", "defaults.yaml"]
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
        SetEnvironmentVariable("WAREHOUSE_TOPIC_PROFILE", "isaac_ros_nvblox_stereo"),
        OpaqueFunction(function=_validate_required_commands),
    ]

    for env_name in (*_REQUIRED_STACK_COMMANDS, "WAREHOUSE_RVIZ_LAUNCH_CMD"):
        process = _process_from_env(env_name)
        if process is not None:
            actions.append(process)

    actions.extend(
        [
            _helper_node("warehouse_health_monitor", "warehouse_health_monitor"),
            _helper_node("warehouse_vision_mavlink_bridge", "warehouse_vision_mavlink_bridge"),
            _helper_node("warehouse_artifact_exporter", "warehouse_artifact_exporter"),
        ]
    )
    return LaunchDescription(actions)
