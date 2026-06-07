from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


BASE_FRAME = "iris_with_standoffs/base_link"
MID360_FRAME = "iris_rplidar_rgbd/mid360_lidar_link/mid360_lidar"
RGBD_FRAME = "iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera"
IMU_FRAME = "imu_link"


def static_tf_node(name, x, y, z, roll, pitch, yaw, parent, child):
    return Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name=name,
        output="screen",
        arguments=[
            "--x", str(x),
            "--y", str(y),
            "--z", str(z),
            "--roll", str(roll),
            "--pitch", str(pitch),
            "--yaw", str(yaw),
            "--frame-id", parent,
            "--child-frame-id", child,
        ],
        parameters=[
            {"use_sim_time": True}
        ],
    )


def generate_launch_description():
    pkg_share = Path(get_package_share_directory("drone_gz_bridge"))
    bridge_config = pkg_share / "config" / "warehouse_bridge.yaml"

    return LaunchDescription([
        Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            name="warehouse_gz_bridge",
            output="screen",
            parameters=[
                {
                    "config_file": str(bridge_config),
                    "use_sim_time": True,
                }
            ],
        ),

        Node(
            package="drone_gz_bridge",
            executable="odom_to_tf",
            name="warehouse_odom_to_tf",
            output="screen",
            parameters=[
                {
                    "use_sim_time": True,
                    "odom_topic": "/warehouse/drone/odometry",
                }
            ],
        ),

        static_tf_node(
            name="base_to_mid360_tf",
            x=0.15,
            y=0.0,
            z=0.08,
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
            parent=BASE_FRAME,
            child=MID360_FRAME,
        ),

        static_tf_node(
            name="base_to_rgbd_tf",
            x=0.20,
            y=0.0,
            z=0.05,
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
            parent=BASE_FRAME,
            child=RGBD_FRAME,
        ),

        static_tf_node(
            name="base_to_imu_tf",
            x=0.0,
            y=0.0,
            z=0.0,
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
            parent=BASE_FRAME,
            child=IMU_FRAME,
        ),
    ])