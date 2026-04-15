from __future__ import annotations

from backend.ros2_irrigation.common import get_ops_health, json_message, require_ros2
from backend.ros2_irrigation.topics import DRONE_STATE_TOPIC


def main() -> None:
    require_ros2()
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    class TelemetryStateNode(Node):
        def __init__(self) -> None:
            super().__init__("telemetry_state_node")
            self.publisher = self.create_publisher(String, DRONE_STATE_TOPIC, 10)
            self.create_timer(0.5, self.publish_state)
            self.get_logger().info(f"Publishing normalized state on {DRONE_STATE_TOPIC}")

        def publish_state(self) -> None:
            payload = get_ops_health()
            telemetry = payload.get("telemetry") or {}
            active_mission = payload.get("active_mission") or {}
            position = ((payload.get("runtime_metrics") or {}).get("position") or {})
            self.publisher.publish(
                json_message(
                    {
                        "timestamp_utc": payload.get("generated_at"),
                        "lat": position.get("lat"),
                        "lon": position.get("lon") or position.get("lng"),
                        "alt_m": position.get("relative_alt") or position.get("alt"),
                        "yaw_deg": (payload.get("runtime_metrics") or {}).get("heading"),
                        "pitch_deg": None,
                        "roll_deg": None,
                        "waypoint_seq": None,
                        "source_connected": telemetry.get("source_connected", False),
                        "mission_id": active_mission.get("flight_id"),
                        "mission_state": active_mission.get("state"),
                    }
                )
            )

    rclpy.init()
    node = TelemetryStateNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
