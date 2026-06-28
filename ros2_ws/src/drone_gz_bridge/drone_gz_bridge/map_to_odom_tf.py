import rclpy
from geometry_msgs.msg import Transform, TransformStamped
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class MapToOdomTf(Node):
    """Publish warehouse_map -> odom from parameters and live localization updates."""

    def __init__(self) -> None:
        super().__init__("warehouse_map_to_odom_tf")

        self.declare_parameter("parent_frame", "warehouse_map")
        self.declare_parameter("child_frame", "odom")
        self.declare_parameter("translation_x", 0.0)
        self.declare_parameter("translation_y", 0.0)
        self.declare_parameter("translation_z", 0.0)
        self.declare_parameter("rotation_x", 0.0)
        self.declare_parameter("rotation_y", 0.0)
        self.declare_parameter("rotation_z", 0.0)
        self.declare_parameter("rotation_w", 1.0)
        self.declare_parameter("publish_rate_hz", 20.0)
        self.declare_parameter("update_topic", "/warehouse/localization/map_to_odom")

        self._parent_frame = str(self.get_parameter("parent_frame").value).strip()
        self._child_frame = str(self.get_parameter("child_frame").value).strip()
        self._transform = self._load_transform_from_parameters()
        self._broadcaster = TransformBroadcaster(self)

        update_topic = str(self.get_parameter("update_topic").value).strip()
        self.create_subscription(
            TransformStamped,
            update_topic,
            self._on_transform_update,
            10,
        )

        rate_hz = max(1.0, float(self.get_parameter("publish_rate_hz").value))
        self.create_timer(1.0 / rate_hz, self._publish)

        self.get_logger().info(
            f"Publishing dynamic TF {self._parent_frame} -> {self._child_frame} "
            f"(updates on {update_topic})"
        )

    def _load_transform_from_parameters(self) -> Transform:
        transform = Transform()
        transform.translation.x = float(self.get_parameter("translation_x").value)
        transform.translation.y = float(self.get_parameter("translation_y").value)
        transform.translation.z = float(self.get_parameter("translation_z").value)
        transform.rotation.x = float(self.get_parameter("rotation_x").value)
        transform.rotation.y = float(self.get_parameter("rotation_y").value)
        transform.rotation.z = float(self.get_parameter("rotation_z").value)
        transform.rotation.w = float(self.get_parameter("rotation_w").value)
        return transform

    def _on_transform_update(self, message: TransformStamped) -> None:
        parent = str(message.header.frame_id or "").strip().lstrip("/")
        child = str(message.child_frame_id or "").strip().lstrip("/")
        if parent != self._parent_frame or child != self._child_frame:
            self.get_logger().warning(
                f"Ignoring map_to_odom update with unexpected frames {parent} -> {child}"
            )
            return
        self._transform = message.transform
        self.get_logger().info(
            f"Updated {self._parent_frame} -> {self._child_frame} transform from localization topic"
        )

    def _publish(self) -> None:
        message = TransformStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = self._parent_frame
        message.child_frame_id = self._child_frame
        message.transform = self._transform
        self._broadcaster.sendTransform(message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MapToOdomTf()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
