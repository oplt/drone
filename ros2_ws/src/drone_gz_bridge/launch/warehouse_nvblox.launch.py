# warehouse_nvblox.launch.py
#
# Launch Isaac ROS Nvblox for the drone_app Gazebo warehouse simulation.
#
# This version is tuned for the current warehouse Gazebo bridge:
#   - bridge publishers are BEST_EFFORT / VOLATILE sensor streams
#   - odometry is nav_msgs/Odometry on /warehouse/drone/odometry
#   - the packaged odom_to_tf node publishes TF using BEST_EFFORT QoS
#   - Nvblox uses TF transforms by default
#
# Place this file at:
#   ros2_ws/src/drone_gz_bridge/launch/warehouse_nvblox.launch.py
#
# Then rebuild/source:
#   cd ros2_ws
#   colcon build --symlink-install --packages-select drone_gz_bridge
#   source install/setup.bash
#
# Backend env example:
#   WAREHOUSE_NVBLOX_LAUNCH_ARGS="use_sim_time:=true run_rviz:=false start_odom_to_tf:=false start_sensor_static_tfs:=false use_tf_transforms:=true use_topic_transforms:=false input_qos:=SENSOR_DATA global_frame:=odom pose_frame:=iris_with_standoffs/base_link"
#
# When warehouse_bridge.launch.py is already running (normal flight path), keep
# start_odom_to_tf and start_sensor_static_tfs false so TF is published once from
# the bridge. Starting a second odom_to_tf here causes sim-time TF buffer jumps.

from __future__ import annotations

from textwrap import dedent

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode
from launch_ros.parameter_descriptions import ParameterValue


# Optional inline fallback adapter.
#
# Default path is the packaged node:
#   ros2 run drone_gz_bridge odom_to_tf
#
# Keep this inline adapter only for topic-pose mode or emergency debugging. It now uses
# BEST_EFFORT QoS so it can subscribe to ros_gz_bridge SENSOR_DATA publishers.
_ODOM_TO_POSE_INLINE = dedent(
    """
    import sys

    import rclpy
    from geometry_msgs.msg import PoseStamped, TransformStamped
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
    from tf2_ros import TransformBroadcaster


    class OdomToPose(Node):
        def __init__(self):
            super().__init__('warehouse_odom_to_pose')
            self.odom_topic = sys.argv[1]
            self.pose_topic = sys.argv[2]
            self.default_parent_frame = sys.argv[3]
            self.default_child_frame = sys.argv[4]

            sensor_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
            )

            self.pose_pub = self.create_publisher(
                PoseStamped,
                self.pose_topic,
                sensor_qos,
            )
            self.tf_broadcaster = TransformBroadcaster(self)
            self.sub = self.create_subscription(
                Odometry,
                self.odom_topic,
                self._on_odom,
                sensor_qos,
            )
            self.get_logger().info(
                f'Converting {self.odom_topic} -> {self.pose_topic} and TF with BEST_EFFORT QoS'
            )

        def _on_odom(self, msg: Odometry):
            parent_frame = msg.header.frame_id or self.default_parent_frame
            child_frame = msg.child_frame_id or self.default_child_frame

            pose = PoseStamped()
            pose.header = msg.header
            pose.header.frame_id = parent_frame
            pose.pose = msg.pose.pose
            self.pose_pub.publish(pose)

            transform = TransformStamped()
            transform.header = msg.header
            transform.header.frame_id = parent_frame
            transform.child_frame_id = child_frame
            transform.transform.translation.x = msg.pose.pose.position.x
            transform.transform.translation.y = msg.pose.pose.position.y
            transform.transform.translation.z = msg.pose.pose.position.z
            transform.transform.rotation = msg.pose.pose.orientation
            self.tf_broadcaster.sendTransform(transform)


    def main():
        rclpy.init()
        node = OdomToPose()
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        finally:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()


    if __name__ == '__main__':
        main()
    """
).strip()

BASE_FRAME = "iris_with_standoffs/base_link"
MID360_FRAME = "iris_rplidar_rgbd/mid360_lidar_link/mid360_lidar"
RGBD_FRAME = "iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera"
IMU_FRAME = "imu_link"


def static_tf_node(name, x, y, z, roll, pitch, yaw, parent, child, use_sim_time, *, condition=None):
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
            {"use_sim_time": ParameterValue(use_sim_time, value_type=bool)},
        ],
        condition=condition,
    )


def generate_launch_description() -> LaunchDescription:
    # NVIDIA's examples provide the maintained Nvblox parameter presets.
    # We reuse those configs, then override only the values specific to this Gazebo warehouse.
    nvblox_examples_share = get_package_share_directory('nvblox_examples_bringup')
    nvblox_base_config = f'{nvblox_examples_share}/config/nvblox/nvblox_base.yaml'
    nvblox_sim_config = f'{nvblox_examples_share}/config/nvblox/specializations/nvblox_sim.yaml'

    use_sim_time = LaunchConfiguration('use_sim_time')
    run_rviz = LaunchConfiguration('run_rviz')

    container_name = LaunchConfiguration('container_name')

    odom_topic = LaunchConfiguration('odom_topic')
    pose_topic = LaunchConfiguration('pose_topic')
    parent_frame = LaunchConfiguration('parent_frame')
    child_frame = LaunchConfiguration('child_frame')
    global_frame = LaunchConfiguration('global_frame')
    pose_frame = LaunchConfiguration('pose_frame')
    input_qos = LaunchConfiguration('input_qos')

    depth_image_topic = LaunchConfiguration('depth_image_topic')
    depth_camera_info_topic = LaunchConfiguration('depth_camera_info_topic')
    color_image_topic = LaunchConfiguration('color_image_topic')
    color_camera_info_topic = LaunchConfiguration('color_camera_info_topic')
    lidar_pointcloud_topic = LaunchConfiguration('lidar_pointcloud_topic')

    nvblox_node = ComposableNode(
        package='nvblox_ros',
        plugin='nvblox::NvbloxNode',
        name='nvblox_node',
        namespace='',
        remappings=[
            # Isaac ROS Nvblox input contract.
            ('camera_0/depth/image', depth_image_topic),
            ('camera_0/depth/camera_info', depth_camera_info_topic),
            ('camera_0/color/image', color_image_topic),
            ('camera_0/color/camera_info', color_camera_info_topic),
            ('pointcloud', lidar_pointcloud_topic),

            # Only used when use_topic_transforms:=true and start_odom_to_pose:=true.
            ('pose', pose_topic),
        ],
        parameters=[
            nvblox_base_config,
            nvblox_sim_config,
            {
                'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
                'num_cameras': 1,

                # Required for ros_gz_bridge SENSOR_DATA publishers, which show up as
                # BEST_EFFORT / VOLATILE in `ros2 topic info -v`.
                'input_qos': ParameterValue(input_qos, value_type=str),

                # Keep frames explicit so Nvblox does not start with neither TF nor
                # topic transforms configured.
                'global_frame': global_frame,
                'pose_frame': pose_frame,
                'map_clearing_frame_id': pose_frame,
                'use_tf_transforms': ParameterValue(
                    LaunchConfiguration('use_tf_transforms'),
                    value_type=bool,
                ),
                'use_topic_transforms': ParameterValue(
                    LaunchConfiguration('use_topic_transforms'),
                    value_type=bool,
                ),

                # Your bridge has both RGB-D and Mid360 pointclouds.
                # Keep this true unless /warehouse/mid360/points is not publishing.
                'use_lidar': ParameterValue(
                    LaunchConfiguration('use_lidar'),
                    value_type=bool,
                ),

                # Output rates kept moderate for local dev.
                'mesh_update_rate_hz': ParameterValue(
                    LaunchConfiguration('mesh_update_rate_hz'),
                    value_type=float,
                ),
                'esdf_update_rate_hz': ParameterValue(
                    LaunchConfiguration('esdf_update_rate_hz'),
                    value_type=float,
                ),
            },
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument('use_sim_time', default_value='true'),
            DeclareLaunchArgument('run_rviz', default_value='false'),

            DeclareLaunchArgument('container_name', default_value='nvblox_container'),
            DeclareLaunchArgument('use_lidar', default_value='true'),

            # Default to TF mode using the packaged odom_to_tf node.
            DeclareLaunchArgument('use_tf_transforms', default_value='true'),
            DeclareLaunchArgument('use_topic_transforms', default_value='false'),
            DeclareLaunchArgument('input_qos', default_value='SENSOR_DATA'),
            DeclareLaunchArgument('global_frame', default_value='odom'),
            DeclareLaunchArgument('pose_frame', default_value='iris_with_standoffs/base_link'),

            DeclareLaunchArgument('mesh_update_rate_hz', default_value='1.0'),
            DeclareLaunchArgument('esdf_update_rate_hz', default_value='2.0'),

            # Gazebo bridge topics from ros2_ws/src/drone_gz_bridge/config/warehouse_bridge.yaml
            DeclareLaunchArgument('odom_topic', default_value='/warehouse/drone/odometry'),
            DeclareLaunchArgument('pose_topic', default_value='/warehouse/drone/pose'),
            DeclareLaunchArgument('parent_frame', default_value='odom'),
            DeclareLaunchArgument('child_frame', default_value='iris_with_standoffs/base_link'),

            DeclareLaunchArgument(
                'depth_image_topic',
                default_value='/warehouse/front/rgbd/depth_image',
            ),
            DeclareLaunchArgument(
                'depth_camera_info_topic',
                default_value='/warehouse/front/rgbd/camera_info',
            ),
            DeclareLaunchArgument(
                'color_image_topic',
                default_value='/warehouse/front/rgbd/image',
            ),
            DeclareLaunchArgument(
                'color_camera_info_topic',
                default_value='/warehouse/front/rgbd/camera_info',
            ),
            DeclareLaunchArgument(
                'lidar_pointcloud_topic',
                default_value='/warehouse/mid360/points',
            ),

            # Disabled by default: warehouse_bridge.launch.py already publishes
            # odom->base_link TF. A duplicate broadcaster breaks sim-time TF sync.
            DeclareLaunchArgument('start_odom_to_tf', default_value='false'),

            # Disabled by default for the same reason: bridge publishes sensor TFs.
            # Enable both flags only for standalone nvblox bring-up without the bridge.
            DeclareLaunchArgument('start_sensor_static_tfs', default_value='false'),

            # Optional fallback adapter: also publishes /warehouse/drone/pose.
            # Keep disabled by default to avoid duplicate TF broadcasters.
            DeclareLaunchArgument('start_odom_to_pose', default_value='false'),

            Node(
                package='drone_gz_bridge',
                executable='odom_to_tf',
                name='warehouse_nvblox_odom_to_tf',
                output='screen',
                parameters=[
                    {'use_sim_time': ParameterValue(use_sim_time, value_type=bool)},
                    {'odom_topic': odom_topic},
                ],
                condition=IfCondition(LaunchConfiguration('start_odom_to_tf')),
            ),

            static_tf_node(
                name='nvblox_base_to_mid360_tf',
                x=0.15,
                y=0.0,
                z=0.08,
                roll=0.0,
                pitch=0.0,
                yaw=0.0,
                parent=BASE_FRAME,
                child=MID360_FRAME,
                use_sim_time=use_sim_time,
                condition=IfCondition(LaunchConfiguration('start_sensor_static_tfs')),
            ),
            static_tf_node(
                name='nvblox_base_to_rgbd_tf',
                x=0.20,
                y=0.0,
                z=0.05,
                roll=0.0,
                pitch=0.0,
                yaw=0.0,
                parent=BASE_FRAME,
                child=RGBD_FRAME,
                use_sim_time=use_sim_time,
                condition=IfCondition(LaunchConfiguration('start_sensor_static_tfs')),
            ),
            static_tf_node(
                name='nvblox_base_to_imu_tf',
                x=0.0,
                y=0.0,
                z=0.0,
                roll=0.0,
                pitch=0.0,
                yaw=0.0,
                parent=BASE_FRAME,
                child=IMU_FRAME,
                use_sim_time=use_sim_time,
                condition=IfCondition(LaunchConfiguration('start_sensor_static_tfs')),
            ),

            ExecuteProcess(
                cmd=[
                    'python3',
                    '-c',
                    _ODOM_TO_POSE_INLINE,
                    odom_topic,
                    pose_topic,
                    parent_frame,
                    child_frame,
                ],
                output='screen',
                condition=IfCondition(LaunchConfiguration('start_odom_to_pose')),
            ),

            ComposableNodeContainer(
                name=container_name,
                namespace='',
                package='rclcpp_components',
                executable='component_container_mt',
                composable_node_descriptions=[nvblox_node],
                output='screen',
                emulate_tty=True,
                parameters=[
                    {'use_sim_time': ParameterValue(use_sim_time, value_type=bool)},
                ],
            ),

            Node(
                package='rviz2',
                executable='rviz2',
                name='rviz2',
                output='screen',
                condition=IfCondition(run_rviz),
                parameters=[
                    {'use_sim_time': ParameterValue(use_sim_time, value_type=bool)},
                ],
            ),
        ]
    )