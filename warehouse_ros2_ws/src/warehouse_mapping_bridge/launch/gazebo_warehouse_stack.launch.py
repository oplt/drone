from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import PathJoinSubstitution
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _validate_gazebo_args(context, *_args, **_kwargs) -> list[ExecuteProcess]:
    start_gazebo = LaunchConfiguration("start_gazebo").perform(context).strip().lower()
    world = LaunchConfiguration("world").perform(context).strip()
    if start_gazebo in {"1", "true", "yes", "on"} and not world:
        raise RuntimeError("gazebo_warehouse_stack.launch.py requires world:=/path/to/world.sdf")
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
    rosbridge_port = LaunchConfiguration("rosbridge_port")
    world = LaunchConfiguration("world")
    default_world = PathJoinSubstitution(
        [FindPackageShare("warehouse_mapping_bridge"), "worlds", "warehouse_empty.sdf"]
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
            ExecuteProcess(
                cmd=["gz", "sim", "-r", world],
                output="screen",
                name="gz_sim",
                condition=IfCondition(LaunchConfiguration("start_gazebo")),
            ),
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="warehouse_gz_parameter_bridge",
                output="screen",
                arguments=[
                    "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
                    "/warehouse/front/rgbd/image@sensor_msgs/msg/Image[gz.msgs.Image",
                    "/warehouse/front/rgbd/depth_image@sensor_msgs/msg/Image[gz.msgs.Image",
                    "/warehouse/front/rgbd/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo",
                    "/warehouse/front/rgbd/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked",
                    "/warehouse/drone/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry",
                    "/world/iris_warehouse/model/iris_rplidar_rgbd/model/iris_with_standoffs/link/imu_link/sensor/imu_sensor/imu@sensor_msgs/msg/Imu[gz.msgs.IMU",
                ],
                condition=IfCondition(LaunchConfiguration("start_bridges")),
            ),
            _helper_node("warehouse_bridge_service", "warehouse_bridge_service"),
            _helper_node("warehouse_sim_tf_broadcaster", "warehouse_sim_tf_broadcaster"),
            _helper_node("warehouse_odometry_export", "warehouse_odometry_export"),
            _helper_node("warehouse_health_monitor", "warehouse_health_monitor"),
            _helper_node("warehouse_artifact_exporter", "warehouse_artifact_exporter"),
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "launch",
                    "rosbridge_server",
                    "rosbridge_websocket_launch.xml",
                    ["port:=", rosbridge_port],
                ],
                output="screen",
                name="rosbridge_websocket",
            ),
        ]
    )
