from __future__ import annotations

from pathlib import Path

import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import Command, PathJoinSubstitution, TextSubstitution
from launch.substitutions import LaunchConfiguration
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _package_file(*parts: str) -> Path:
    return Path(__file__).resolve().parents[1].joinpath(*parts)


def _bridge_argument(mapping: dict[str, str]) -> str:
    direction = str(mapping.get("direction", "GZ_TO_ROS")).upper()
    ros_topic = mapping["ros_topic_name"]
    gz_topic = mapping.get("gz_topic_name", ros_topic)
    ros_type = mapping["ros_type_name"]
    gz_type = mapping["gz_type_name"]
    if ros_topic != gz_topic:
        raise RuntimeError(
            "ros_gz_bridge parameter_bridge cannot express different ROS/Gazebo "
            f"topic names without remapping: {ros_topic} != {gz_topic}"
        )
    separator = {
        "GZ_TO_ROS": "[",
        "ROS_TO_GZ": "]",
        "BIDIRECTIONAL": "@",
    }.get(direction)
    if separator is None:
        raise RuntimeError(f"Unsupported Gazebo bridge direction: {direction}")
    return f"{ros_topic}@{ros_type}{separator}{gz_type}"


def _gazebo_bridge_arguments() -> list[str]:
    path = _package_file("config", "gazebo_bridge.yaml")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(payload, list):
        raise RuntimeError(f"{path} must contain a list of bridge mappings")
    return [_bridge_argument(mapping) for mapping in payload]


def _validate_gazebo_args(context, *_args, **_kwargs) -> list[ExecuteProcess]:
    start_gazebo = LaunchConfiguration("start_gazebo").perform(context).strip().lower()
    world = LaunchConfiguration("world").perform(context).strip()
    if start_gazebo in {"1", "true", "yes", "on"} and not world:
        raise RuntimeError("gazebo_warehouse_stack.launch.py requires world:=/path/to/world.sdf")
    return []


def _helper_node(executable: str, name: str) -> Node:
    default_params = PathJoinSubstitution(
        [FindPackageShare("warehouse_mapping_bridge"), "config", "defaults_gazebo.yaml"]
    )
    return Node(
        package="warehouse_mapping_bridge",
        executable=executable,
        name=name,
        output="screen",
        parameters=[default_params, {"use_sim_time": LaunchConfiguration("use_sim_time")}],
    )


def generate_launch_description() -> LaunchDescription:
    rosbridge_port = LaunchConfiguration("rosbridge_port")
    world = LaunchConfiguration("world")
    default_world = PathJoinSubstitution(
        [FindPackageShare("warehouse_mapping_bridge"), "worlds", "warehouse_empty.sdf"]
    )
    drone_urdf = PathJoinSubstitution(
        [FindPackageShare("warehouse_mapping_bridge"), "urdf", "warehouse_drone.urdf"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("world", default_value=default_world, description="Gazebo world path"),
            DeclareLaunchArgument("start_gazebo", default_value="true"),
            DeclareLaunchArgument("start_bridges", default_value="true"),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("rosbridge_port", default_value="9090"),
            OpaqueFunction(function=_validate_gazebo_args),
            SetEnvironmentVariable("WAREHOUSE_GAZEBO_SIM", "1"),
            SetEnvironmentVariable("WAREHOUSE_TOPIC_PROFILE", "gazebo"),
            SetEnvironmentVariable(
                "GZ_SIM_RESOURCE_PATH",
                PathJoinSubstitution([FindPackageShare("warehouse_mapping_bridge"), "models"]),
            ),
            ExecuteProcess(
                cmd=["gz", "sim", "-r", world],
                output="screen",
                name="gz_sim",
                condition=IfCondition(LaunchConfiguration("start_gazebo")),
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="warehouse_robot_state_publisher",
                output="screen",
                parameters=[
                    {
                        "use_sim_time": LaunchConfiguration("use_sim_time"),
                        "robot_description": ParameterValue(
                            Command([TextSubstitution(text="cat "), drone_urdf]),
                            value_type=str,
                        ),
                    }
                ],
            ),
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="warehouse_gz_parameter_bridge",
                output="screen",
                arguments=_gazebo_bridge_arguments(),
                condition=IfCondition(LaunchConfiguration("start_bridges")),
            ),
            _helper_node("warehouse_topic_adapter", "warehouse_topic_adapter"),
            _helper_node("warehouse_bridge_service", "warehouse_bridge_service"),
            _helper_node("warehouse_sim_tf_broadcaster", "warehouse_sim_tf_broadcaster"),
            _helper_node("warehouse_odometry_export", "warehouse_odometry_export"),
            _helper_node("warehouse_health_monitor", "warehouse_health_monitor"),
            _helper_node("warehouse_artifact_exporter", "warehouse_artifact_exporter"),
            _helper_node("warehouse_diagnostics_aggregator", "warehouse_diagnostics_aggregator"),
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "launch",
                    "rosbridge_server",
                    "rosbridge_websocket_launch.xml",
                    [TextSubstitution(text="port:="), rosbridge_port],
                ],
                output="screen",
                name="rosbridge_websocket",
            ),
        ]
    )
