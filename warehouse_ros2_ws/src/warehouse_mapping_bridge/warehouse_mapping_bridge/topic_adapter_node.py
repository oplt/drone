from __future__ import annotations

import os

from .config import source_topic_env, topic_env, topic_registry
from .ros_node_utils import configure_use_sim_time

# Gazebo contract sensors are published by start_gazebo_sensor_bridge.sh (gz + relay).
_GAZEBO_DIRECT_CONTRACT_KEYS = frozenset(
    {
        "rgb_image",
        "left_image",
        "right_image",
        "depth",
        "raw_lidar",
        "visual_slam_odom",
        "rgb_camera_info",
        "depth_camera_info",
        "camera_info",
        "imu",
    }
)


def _gazebo_direct_contract_bridge_enabled(profile: str) -> bool:
    if profile != "gazebo":
        return False
    return os.getenv("WAREHOUSE_GAZEBO_DIRECT_CONTRACT_BRIDGE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def normalize_odometry_frames(
    message: object, *, odom_frame: str, base_link_frame: str
) -> object:
    message.header.frame_id = odom_frame
    message.child_frame_id = base_link_frame
    return message


def main() -> None:
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import CameraInfo, Image, Imu, PointCloud2

    class WarehouseTopicAdapter(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_topic_adapter")
            configure_use_sim_time(self)
            profile = os.getenv("WAREHOUSE_TOPIC_PROFILE", topic_registry().profile)
            self.declare_parameter("profile", profile)
            self.profile = str(self.get_parameter("profile").value or profile)
            self.source_topics = source_topic_env(self.profile)
            self.contract_topics = topic_env()
            registry_frames = topic_registry().frames
            self.odom_frame = os.getenv(
                "WAREHOUSE_ODOM_FRAME",
                registry_frames.get("odom", "odom"),
            )
            self.base_link_frame = os.getenv(
                "WAREHOUSE_BASE_LINK_FRAME",
                registry_frames.get("base_link", "base_link"),
            )
            self._publishers: list[object] = []
            self._subscriptions: list[object] = []
            sensor_qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
            reliable_qos = QoSProfile(depth=20)
            self._relay("rgb_image", Image, sensor_qos)
            self._relay("left_image", Image, sensor_qos)
            self._relay("right_image", Image, sensor_qos)
            self._relay("depth", Image, sensor_qos)
            self._relay("raw_lidar", PointCloud2, sensor_qos)
            self._relay("pointcloud", PointCloud2, sensor_qos)
            self._relay("imu", Imu, sensor_qos)
            self._relay("mesh_marker", object, reliable_qos)
            self._relay("camera_info", CameraInfo, sensor_qos)
            self._relay("rgb_camera_info", CameraInfo, sensor_qos)
            self._relay("depth_camera_info", CameraInfo, sensor_qos)
            self._relay_odometry("visual_slam_odom", Odometry, sensor_qos, reliable_qos)
            # local_odometry is owned by warehouse_odometry_export (single contract publisher).
            self.get_logger().info(
                f"Warehouse topic adapter profile={self.profile} "
                f"source_to_contract={self.source_topics}"
            )

        def _relay(self, key: str, message_type: object, qos: QoSProfile) -> None:
            if _gazebo_direct_contract_bridge_enabled(self.profile) and key in _GAZEBO_DIRECT_CONTRACT_KEYS:
                return
            source = self.source_topics.get(key, "")
            target = self.contract_topics.get(key, "")
            if not source or not target or source == target:
                return
            if message_type is object:
                return
            publisher = self.create_publisher(message_type, target, qos)
            self._publishers.append(publisher)
            self._subscriptions.append(
                self.create_subscription(
                    message_type,
                    source,
                    lambda message, pub=publisher: pub.publish(message),
                    qos,
                )
            )

        def _relay_odometry(
            self,
            key: str,
            message_type: object,
            sub_qos: QoSProfile,
            pub_qos: QoSProfile,
        ) -> None:
            if _gazebo_direct_contract_bridge_enabled(self.profile) and key in _GAZEBO_DIRECT_CONTRACT_KEYS:
                return
            source = self.source_topics.get(key, "")
            target = self.contract_topics.get(key, "")
            if not source or not target or source == target:
                return
            publisher = self.create_publisher(message_type, target, pub_qos)
            self._publishers.append(publisher)
            self._subscriptions.append(
                self.create_subscription(
                    message_type,
                    source,
                    lambda message, pub=publisher: pub.publish(
                        normalize_odometry_frames(
                            message,
                            odom_frame=self.odom_frame,
                            base_link_frame=self.base_link_frame,
                        )
                    ),
                    sub_qos,
                )
            )
            self.get_logger().info(
                f"Relaying odometry {source} -> {target} frames="
                f"{self.odom_frame}->{self.base_link_frame}"
            )

    rclpy.init()
    node = WarehouseTopicAdapter()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
