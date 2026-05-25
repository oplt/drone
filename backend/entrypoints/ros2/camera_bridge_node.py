from __future__ import annotations

from backend.entrypoints.ros2.common import require_ros2, ros_camera_input_topic
from backend.entrypoints.ros2.topics import CAMERA_IMAGE_TOPIC


def main() -> None:
    require_ros2()
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image

    class CameraBridgeNode(Node):
        def __init__(self) -> None:
            super().__init__("camera_bridge_node")
            discovered_topic = ros_camera_input_topic()
            input_topic = self.declare_parameter("input_topic", discovered_topic).value
            output_topic = self.declare_parameter("output_topic", CAMERA_IMAGE_TOPIC).value
            self.publisher = self.create_publisher(Image, output_topic, 10)
            self.subscription = self.create_subscription(Image, input_topic, self.forward, 10)
            self.get_logger().info(f"Republishing {input_topic} -> {output_topic}")

        def forward(self, message: Image) -> None:
            self.publisher.publish(message)

    rclpy.init()
    node = CameraBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
