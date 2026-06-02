from __future__ import annotations

import os
import shlex

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

from warehouse_mapping_bridge.isaac_stack_contract import (
    load_stack_commands,
    missing_required_commands,
)


def _process_from_command(env_name: str, command: str) -> ExecuteProcess | None:
    if not command.strip():
        return None
    cmd = shlex.split(command)
    if not cmd:
        return None
    return ExecuteProcess(cmd=cmd, output="screen", name=env_name)


def _validate_required_commands(_context, *_args, **_kwargs) -> list[ExecuteProcess]:
    if os.getenv("WAREHOUSE_ALLOW_PARTIAL_ISAAC_LAUNCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return []
    commands = load_stack_commands()
    missing = missing_required_commands(commands)
    if missing:
        joined = ", ".join(command.env for command in missing)
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
    stack_commands = load_stack_commands()
    actions = [
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        SetEnvironmentVariable("WAREHOUSE_TOPIC_PROFILE", "isaac_ros_nvblox_stereo"),
        OpaqueFunction(function=_validate_required_commands),
    ]

    for stack_command in stack_commands:
        process = _process_from_command(stack_command.env, stack_command.command)
        if process is not None:
            actions.append(process)

    actions.extend(
        [
            _helper_node("warehouse_isaac_stack_preflight", "warehouse_isaac_stack_preflight"),
            _helper_node("warehouse_topic_adapter", "warehouse_topic_adapter"),
            _helper_node("warehouse_health_monitor", "warehouse_health_monitor"),
            _helper_node("warehouse_vision_mavlink_bridge", "warehouse_vision_mavlink_bridge"),
            _helper_node("warehouse_artifact_exporter", "warehouse_artifact_exporter"),
            _helper_node("warehouse_diagnostics_aggregator", "warehouse_diagnostics_aggregator"),
        ]
    )
    return LaunchDescription(actions)
