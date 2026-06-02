from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime

from .config import topic_env, topic_registry


def main() -> None:
    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import Image, Imu, PointCloud2
    from std_msgs.msg import String

    class WarehouseHealthMonitor(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_health_monitor")
            self.topics = topic_env()
            for key, value in list(self.topics.items()):
                if key.endswith("_compressed"):
                    continue
                self.declare_parameter(f"{key}_topic", value)
                self.topics[key] = str(self.get_parameter(f"{key}_topic").value or value)
            self.publisher = self.create_publisher(String, self.topics["health"], QoSProfile(depth=10))
            self.diagnostics_publisher = self.create_publisher(
                DiagnosticArray,
                "/warehouse/mapping/diagnostics",
                QoSProfile(depth=10),
            )
            self.declare_parameter(
                "required_topic_stale_after_s",
                float(os.getenv("WAREHOUSE_HEALTH_TOPIC_STALE_AFTER_S", "3.0")),
            )
            self.stale_after_s = max(0.1, float(self.get_parameter("required_topic_stale_after_s").value))
            self.last_seen: dict[str, float] = {}
            self.message_counts: dict[str, int] = {}
            self.required_topic_types = {
                "rgb_image": Image,
                "left_image": Image,
                "right_image": Image,
                "depth": Image,
                "imu": Imu,
                "visual_slam_odom": Odometry,
                "local_odometry": Odometry,
                "raw_lidar": PointCloud2,
                "pointcloud": PointCloud2,
            }
            sensor_qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
            reliable_qos = QoSProfile(depth=20)
            registry = topic_registry()
            for key in (*registry.required_for_perception, "pointcloud"):
                topic = self.topics.get(key)
                message_type = self.required_topic_types.get(key)
                if not topic or message_type is None:
                    continue
                qos = reliable_qos if key in {"visual_slam_odom", "local_odometry"} else sensor_qos
                self.create_subscription(
                    message_type,
                    topic,
                    lambda _message, topic_key=key: self._mark_seen(topic_key),
                    qos,
                )
            self.create_timer(1.0, self.publish_health)

        def _mark_seen(self, key: str) -> None:
            self.last_seen[key] = time.monotonic()
            self.message_counts[key] = self.message_counts.get(key, 0) + 1

        def publish_health(self) -> None:
            discovered = {
                name for name, _types in self.get_topic_names_and_types()
            }
            registry = topic_registry()
            required = {
                key: self.topics[key]
                for key in (*registry.required_for_perception, "pointcloud")
                if self.topics.get(key)
            }
            now_mono = time.monotonic()
            components: dict[str, bool] = {}
            freshness: dict[str, float | None] = {}
            publisher_counts: dict[str, int] = {}
            for key, topic in required.items():
                publisher_count = self.count_publishers(topic)
                publisher_counts[key] = publisher_count
                age = None
                if key in self.last_seen:
                    age = now_mono - self.last_seen[key]
                freshness[key] = age
                components[key] = (
                    topic in discovered
                    and publisher_count > 0
                    and age is not None
                    and age <= self.stale_after_s
                )
            missing = [key for key, healthy in components.items() if not healthy]
            payload = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "ready": not missing,
                "status": "ready" if not missing else "degraded",
                "source": "warehouse_health_monitor",
                "components": components,
                "missing_required_topics": missing,
                "topics": required,
                "topic_age_s": freshness,
                "publisher_counts": publisher_counts,
                "message_counts": self.message_counts,
                "stale_after_s": self.stale_after_s,
            }
            msg = String()
            msg.data = json.dumps(payload, sort_keys=True)
            self.publisher.publish(msg)
            diag = DiagnosticArray()
            diag.header.stamp = self.get_clock().now().to_msg()
            status = DiagnosticStatus()
            status.name = "warehouse_mapping_bridge/health"
            status.hardware_id = "warehouse_mapping_bridge"
            status.level = DiagnosticStatus.OK if not missing else DiagnosticStatus.WARN
            status.message = payload["status"]
            status.values = [
                KeyValue(key="ready", value=str(payload["ready"]).lower()),
                KeyValue(key="missing_required_topics", value=",".join(missing)),
                KeyValue(key="stale_after_s", value=str(self.stale_after_s)),
                *[
                    KeyValue(key=f"topic.{key}", value=str(healthy).lower())
                    for key, healthy in sorted(components.items())
                ],
                *[
                    KeyValue(key=f"topic_age_s.{key}", value="" if value is None else f"{value:.3f}")
                    for key, value in sorted(freshness.items())
                ],
            ]
            diag.status.append(status)
            self.diagnostics_publisher.publish(diag)

    rclpy.init()
    node = WarehouseHealthMonitor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
