from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config, topic_env


def _stamp_to_sec(stamp: object) -> float | None:
    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if sec is None or nanosec is None:
        return None
    return float(sec) + (float(nanosec) / 1_000_000_000.0)


def main() -> None:
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import QoSProfile

    class WarehouseOdometryExport(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_odometry_export")
            self.topics = topic_env()
            self.config = load_config()
            self.declare_parameter("visual_slam_odom_topic", self.topics["visual_slam_odom"])
            self.declare_parameter("local_odometry_topic", self.topics["local_odometry"])
            self.topics["visual_slam_odom"] = str(
                self.get_parameter("visual_slam_odom_topic").value or self.topics["visual_slam_odom"]
            )
            self.topics["local_odometry"] = str(
                self.get_parameter("local_odometry_topic").value or self.topics["local_odometry"]
            )
            self.state_path = Path(
                os.getenv("WAREHOUSE_ODOMETRY_STATE_PATH", str(self.config.odometry_state_path))
            ).expanduser()
            self.declare_parameter("odometry_state_path", str(self.state_path))
            self.state_path = Path(str(self.get_parameter("odometry_state_path").value)).expanduser()
            self.state_write_period_s = max(
                0.05,
                float(os.getenv("WAREHOUSE_ODOMETRY_STATE_WRITE_PERIOD_S", "0.25")),
            )
            self._last_state_write_s = 0.0
            self.publisher = self.create_publisher(
                Odometry,
                self.topics["local_odometry"],
                QoSProfile(depth=20),
            )
            self.create_subscription(
                Odometry,
                self.topics["visual_slam_odom"],
                self.on_odometry,
                QoSProfile(depth=20),
            )

        def on_odometry(self, message: Odometry) -> None:
            position = message.pose.pose.position
            orientation = message.pose.pose.orientation
            linear = message.twist.twist.linear
            angular = message.twist.twist.angular
            now_mono = time.monotonic()
            payload = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "updated_at_monotonic": now_mono,
                "source_stamp_sec": _stamp_to_sec(message.header.stamp),
                "frame_id": message.header.frame_id,
                "child_frame_id": message.child_frame_id,
                "local_north_m": float(position.y),
                "local_east_m": float(position.x),
                "local_down_m": -float(position.z),
                "position": {
                    "x_m": float(position.x),
                    "y_m": float(position.y),
                    "z_m": float(position.z),
                },
                "orientation": {
                    "x": float(orientation.x),
                    "y": float(orientation.y),
                    "z": float(orientation.z),
                    "w": float(orientation.w),
                },
                "velocity": {
                    "x_mps": float(linear.x),
                    "y_mps": float(linear.y),
                    "z_mps": float(linear.z),
                    "yaw_rate_rps": float(angular.z),
                },
                "slam_ready": True,
                "slam_tracking_ok": True,
                "local_position_ok": True,
                "localization_confidence": 1.0,
                "odometry_drift_m": 0.0,
            }
            if now_mono - self._last_state_write_s >= self.state_write_period_s:
                self._last_state_write_s = now_mono
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self.state_path.with_suffix(f"{self.state_path.suffix}.tmp")
                tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
                tmp_path.replace(self.state_path)
            self.publisher.publish(message)

    rclpy.init()
    node = WarehouseOdometryExport()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
