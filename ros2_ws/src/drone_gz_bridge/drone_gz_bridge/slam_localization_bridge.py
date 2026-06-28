import json
import math

import rclpy
from geometry_msgs.msg import Transform, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import String


class SlamLocalizationBridge(Node):
    """Publish live SLAM map_to_odom updates with confidence gating."""

    def __init__(self) -> None:
        super().__init__("warehouse_slam_localization_bridge")
        self.declare_parameter("input_topic", "/visual_slam/tracking/odometry")
        self.declare_parameter("output_topic", "/warehouse/localization/map_to_odom")
        self.declare_parameter("status_topic", "/warehouse/localization/status")
        self.declare_parameter("parent_frame", "warehouse_map")
        self.declare_parameter("child_frame", "odom")
        self.declare_parameter("min_confidence", 0.5)
        self.declare_parameter("max_position_std_m", 1.0)

        input_topic = str(self.get_parameter("input_topic").value).strip()
        output_topic = str(self.get_parameter("output_topic").value).strip()
        status_topic = str(self.get_parameter("status_topic").value).strip()
        self._parent_frame = str(self.get_parameter("parent_frame").value).strip()
        self._child_frame = str(self.get_parameter("child_frame").value).strip()
        self._min_confidence = float(self.get_parameter("min_confidence").value)
        self._max_position_std_m = float(self.get_parameter("max_position_std_m").value)

        self._publisher = self.create_publisher(TransformStamped, output_topic, 10)
        self._status_publisher = self.create_publisher(String, status_topic, 10)
        self.create_subscription(Odometry, input_topic, self._on_odometry, 10)
        self.get_logger().info(
            f"SLAM localization bridge input={input_topic} output={output_topic} "
            f"status={status_topic}"
        )

    def _confidence_from_covariance(self, covariance: list[float]) -> float:
        if len(covariance) < 36:
            return 0.0
        variances = [float(covariance[i]) for i in (0, 7, 14)]
        if any(value < 0.0 for value in variances):
            return 0.0
        max_std = math.sqrt(max(variances))
        if max_std <= 1e-9:
            return 1.0
        if max_std >= self._max_position_std_m:
            return 0.0
        return max(0.0, min(1.0, 1.0 - (max_std / self._max_position_std_m)))

    def _on_odometry(self, message: Odometry) -> None:
        confidence = self._confidence_from_covariance(list(message.pose.covariance))
        pose = message.pose.pose
        transform = Transform()
        transform.translation.x = float(pose.position.x)
        transform.translation.y = float(pose.position.y)
        transform.translation.z = float(pose.position.z)
        transform.rotation = pose.orientation

        stamped = TransformStamped()
        stamped.header = message.header
        stamped.header.frame_id = self._parent_frame
        stamped.child_frame_id = self._child_frame
        stamped.transform = transform

        status = {
            "confidence": confidence,
            "healthy": confidence >= self._min_confidence,
            "transform": {
                "translation": {
                    "x": transform.translation.x,
                    "y": transform.translation.y,
                    "z": transform.translation.z,
                },
                "rotation": {
                    "x": transform.rotation.x,
                    "y": transform.rotation.y,
                    "z": transform.rotation.z,
                    "w": transform.rotation.w,
                },
            },
        }
        self._status_publisher.publish(String(data=json.dumps(status)))
        if confidence < self._min_confidence:
            self.get_logger().warning(
                f"Skipping SLAM map_to_odom update: confidence {confidence:.2f} "
                f"below {self._min_confidence:.2f}"
            )
            return
        self._publisher.publish(stamped)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SlamLocalizationBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
