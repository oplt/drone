from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config, topic_env, topic_registry
from .ros_node_utils import configure_use_sim_time


def normalize_odometry_frames(
    message: object, *, odom_frame: str, base_link_frame: str
) -> object:
    message.header.frame_id = odom_frame
    message.child_frame_id = base_link_frame
    return message


def _stamp_to_sec(stamp: object) -> float | None:
    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if sec is None or nanosec is None:
        return None
    return float(sec) + (float(nanosec) / 1_000_000_000.0)


def _covariance_max_diagonal(covariance: object) -> float | None:
    try:
        values = [float(covariance[index]) for index in (0, 7, 14)]
    except (TypeError, ValueError, IndexError):
        return None
    if not any(values):
        return None
    return max(values)


def main() -> None:
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import QoSProfile

    class WarehouseOdometryExport(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_odometry_export")
            configure_use_sim_time(self)
            self.topics = topic_env()
            self.config = load_config()
            registry_frames = topic_registry().frames
            self.odom_frame = os.getenv(
                "WAREHOUSE_ODOM_FRAME",
                registry_frames.get("odom", "odom"),
            )
            self.base_link_frame = os.getenv(
                "WAREHOUSE_BASE_LINK_FRAME",
                registry_frames.get("base_link", "base_link"),
            )
            self.declare_parameter("visual_slam_odom_topic", self.topics["visual_slam_odom"])
            self.declare_parameter("local_odometry_topic", self.topics["local_odometry"])
            self.declare_parameter("odom_frame", self.odom_frame)
            self.declare_parameter("base_link_frame", self.base_link_frame)
            self.topics["visual_slam_odom"] = str(
                self.get_parameter("visual_slam_odom_topic").value
                or self.topics["visual_slam_odom"]
            )
            self.topics["local_odometry"] = str(
                self.get_parameter("local_odometry_topic").value or self.topics["local_odometry"]
            )
            self.odom_frame = str(self.get_parameter("odom_frame").value or self.odom_frame)
            self.base_link_frame = str(
                self.get_parameter("base_link_frame").value or self.base_link_frame
            )
            self.state_path = Path(
                os.getenv("WAREHOUSE_ODOMETRY_STATE_PATH", str(self.config.odometry_state_path))
            ).expanduser()
            self.declare_parameter("odometry_state_path", str(self.state_path))
            self.state_path = Path(
                str(self.get_parameter("odometry_state_path").value)
            ).expanduser()
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
            message = normalize_odometry_frames(
                message,
                odom_frame=self.odom_frame,
                base_link_frame=self.base_link_frame,
            )
            position = message.pose.pose.position
            orientation = message.pose.pose.orientation
            linear = message.twist.twist.linear
            angular = message.twist.twist.angular
            now_mono = time.monotonic()
            max_position_variance = _covariance_max_diagonal(message.pose.covariance)
            localization_mode = os.getenv("WAREHOUSE_LOCALIZATION_MODE", "").strip().lower()
            gazebo_gt = localization_mode in {
                "",
                "gazebo_ground_truth",
                "gazebo_gt",
                "gazebo",
                "sim",
            } and (
                os.getenv("WAREHOUSE_TOPIC_PROFILE", "").strip().lower() == "gazebo"
                or os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower()
                in {"1", "true", "yes", "on"}
                or os.getenv("WAREHOUSE_BRIDGE_FLOW", "").strip().lower() == "gazebo"
            )
            local_position_ok = (
                max_position_variance is None
                or max_position_variance
                <= float(os.getenv("WAREHOUSE_ODOM_MAX_POSITION_VAR_M2", "4.0"))
            )
            tracking_ok = True if gazebo_gt else bool(local_position_ok)
            tracking_status = (
                "GAZEBO_GROUND_TRUTH_OK"
                if gazebo_gt and tracking_ok
                else ("tracking" if tracking_ok else "covariance_high")
            )
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
                "odom_received": True,
                "slam_ready": tracking_ok,
                "slam_tracking_ok": tracking_ok,
                "slam_tracking_status": tracking_status,
                "localization_mode": (
                    "gazebo_ground_truth" if gazebo_gt else "visual_slam"
                ),
                "local_position_ok": local_position_ok,
                "localization_confidence": None,
                "max_position_variance_m2": max_position_variance,
                "odometry_drift_m": None,
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
