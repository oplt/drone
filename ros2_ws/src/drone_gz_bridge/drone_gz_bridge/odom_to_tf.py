import rclpy
from rclpy.node import Node

from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy


class OdomToTf(Node):
    def __init__(self):
        super().__init__("odom_to_tf")

        self.declare_parameter("odom_topic", "/warehouse/drone/odometry")
        self.declare_parameter("parent_frame_override", "odom")
        self.declare_parameter("child_frame_override", "base_link")
        self.declare_parameter("sensor_calibration_checksum", "")

        self.odom_topic = self.get_parameter("odom_topic").value
        self.parent_frame = str(self.get_parameter("parent_frame_override").value).strip()
        self.child_frame = str(self.get_parameter("child_frame_override").value).strip()
        self.calibration_checksum = str(
            self.get_parameter("sensor_calibration_checksum").value
        ).strip()
        if not self.parent_frame or not self.child_frame:
            raise ValueError("TF frame overrides must be non-empty")
        if len(self.calibration_checksum) != 64:
            raise ValueError("sensor calibration checksum must be SHA-256")
        use_sim_time = (
            bool(self.get_parameter("use_sim_time").value)
            if self.has_parameter("use_sim_time")
            else False
        )
        self.tf_broadcaster = TransformBroadcaster(self)

        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.subscription = self.create_subscription(
            Odometry,
            self.odom_topic,
            self.odom_callback,
            qos,
        )

        self.get_logger().info(
            f"Publishing TF from odometry topic: {self.odom_topic} "
            f"as {self.parent_frame}->{self.child_frame} "
            f"calibration={self.calibration_checksum} (use_sim_time={use_sim_time})"
        )

    def odom_callback(self, msg: Odometry):
        transform = TransformStamped()

        transform.header.stamp = msg.header.stamp
        transform.header.frame_id = self.parent_frame
        transform.child_frame_id = self.child_frame

        transform.transform.translation.x = msg.pose.pose.position.x
        transform.transform.translation.y = msg.pose.pose.position.y
        transform.transform.translation.z = msg.pose.pose.position.z
        transform.transform.rotation = msg.pose.pose.orientation

        self.tf_broadcaster.sendTransform(transform)


def main(args=None):
    rclpy.init(args=args)
    node = OdomToTf()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
