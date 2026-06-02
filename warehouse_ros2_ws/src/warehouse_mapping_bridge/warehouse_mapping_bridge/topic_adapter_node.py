from __future__ import annotations

import os

from .config import source_topic_env, topic_env, topic_registry


def main() -> None:
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import CameraInfo, Image, Imu, PointCloud2

    class WarehouseTopicAdapter(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_topic_adapter")
            profile = os.getenv("WAREHOUSE_TOPIC_PROFILE", topic_registry().profile)
            self.declare_parameter("profile", profile)
            self.profile = str(self.get_parameter("profile").value or profile)
            self.source_topics = source_topic_env(self.profile)
            self.contract_topics = topic_env()
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
            self._relay("visual_slam_odom", Odometry, reliable_qos)
            self._relay("local_odometry", Odometry, reliable_qos)
            self._relay("mesh_marker", object, reliable_qos)
            self._relay("camera_info", CameraInfo, sensor_qos)
            self.get_logger().info(
                f"Warehouse topic adapter profile={self.profile} source_to_contract={self.source_topics}"
            )

        def _relay(self, key: str, message_type: object, qos: QoSProfile) -> None:
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

    rclpy.init()
    node = WarehouseTopicAdapter()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
