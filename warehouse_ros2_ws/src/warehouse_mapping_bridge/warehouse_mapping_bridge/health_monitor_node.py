from __future__ import annotations

import json
from datetime import UTC, datetime

from .config import topic_env


def main() -> None:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    class WarehouseHealthMonitor(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_health_monitor")
            self.topics = topic_env()
            self.publisher = self.create_publisher(String, self.topics["health"], 10)
            self.create_timer(1.0, self.publish_health)

        def publish_health(self) -> None:
            discovered = {
                name for name, _types in self.get_topic_names_and_types()
            }
            required = {
                "rgb_image": self.topics["rgb_image"],
                "left_image": self.topics["left_image"],
                "right_image": self.topics["right_image"],
                "imu": self.topics["imu"],
                "visual_slam_odom": self.topics["visual_slam_odom"],
                "depth": self.topics["depth"],
                "pointcloud": self.topics["pointcloud"],
            }
            components = {
                key: topic in discovered for key, topic in required.items()
            }
            payload = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "ready": None,
                "status": "heartbeat",
                "source": "warehouse_health_monitor",
            }
            msg = String()
            msg.data = json.dumps(payload, sort_keys=True)
            self.publisher.publish(msg)

    rclpy.init()
    node = WarehouseHealthMonitor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
