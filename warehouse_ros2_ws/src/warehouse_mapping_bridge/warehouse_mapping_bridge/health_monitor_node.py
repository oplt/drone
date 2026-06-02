from __future__ import annotations

import json
from datetime import UTC, datetime

from .config import topic_env, topic_registry


def main() -> None:
    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
    from rclpy.node import Node
    from rclpy.qos import QoSProfile
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
            self.create_timer(1.0, self.publish_health)

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
            components = {
                key: topic in discovered for key, topic in required.items()
            }
            missing = [key for key, healthy in components.items() if not healthy]
            payload = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "ready": not missing,
                "status": "ready" if not missing else "degraded",
                "source": "warehouse_health_monitor",
                "components": components,
                "missing_required_topics": missing,
                "topics": required,
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
                *[
                    KeyValue(key=f"topic.{key}", value=str(healthy).lower())
                    for key, healthy in sorted(components.items())
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
