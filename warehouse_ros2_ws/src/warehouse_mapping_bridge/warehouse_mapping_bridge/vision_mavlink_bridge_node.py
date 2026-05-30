from __future__ import annotations

import os

from .config import load_config, topic_env
from .vision_mavlink import odometry_to_vision_pose


def main() -> None:
    import rclpy
    from nav_msgs.msg import Odometry
    from pymavlink import mavutil
    from rclpy.node import Node

    class WarehouseVisionMavlinkBridge(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_vision_mavlink_bridge")
            self.config = load_config()
            self.enabled = os.getenv("WAREHOUSE_SEND_VISION_POSITION", "1").lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            self.mav = None
            if self.enabled:
                self.mav = mavutil.mavlink_connection(
                    self.config.mavlink_vision_url,
                    source_system=int(os.getenv("WAREHOUSE_MAVLINK_SOURCE_SYSTEM", "191")),
                    source_component=int(os.getenv("WAREHOUSE_MAVLINK_SOURCE_COMPONENT", "197")),
                )
                self.get_logger().info(
                    f"Sending VISION_POSITION_ESTIMATE to {self.config.mavlink_vision_url}"
                )
            self.create_subscription(
                Odometry,
                topic_env()["visual_slam_odom"],
                self.on_odometry,
                20,
            )

        def on_odometry(self, message: Odometry) -> None:
            if self.mav is None:
                return
            estimate = odometry_to_vision_pose(message)
            self.mav.mav.vision_position_estimate_send(
                estimate.usec,
                estimate.x_north_m,
                estimate.y_east_m,
                estimate.z_down_m,
                estimate.roll_rad,
                estimate.pitch_rad,
                estimate.yaw_rad,
                estimate.covariance,
                estimate.reset_counter,
            )

    rclpy.init()
    node = WarehouseVisionMavlinkBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
