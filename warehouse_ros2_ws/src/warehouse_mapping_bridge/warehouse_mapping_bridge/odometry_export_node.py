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

    class WarehouseOdometryExport(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_odometry_export")
            self.topics = topic_env()
            self.config = load_config()
            self.state_path = Path(
                os.getenv("WAREHOUSE_ODOMETRY_STATE_PATH", str(self.config.odometry_state_path))
            ).expanduser()
            self.publisher = self.create_publisher(
                Odometry,
                self.topics["local_odometry"],
                20,
            )
            self.create_subscription(
                Odometry,
                self.topics["visual_slam_odom"],
                self.on_odometry,
                20,
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
