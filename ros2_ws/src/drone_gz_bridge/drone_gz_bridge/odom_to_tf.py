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

        self.odom_topic = self.get_parameter("odom_topic").value
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
            f"(use_sim_time={use_sim_time})"
        )

    def odom_callback(self, msg: Odometry):
        if not msg.header.frame_id:
            self.get_logger().warn("Odometry message has empty header.frame_id")
            return

        if not msg.child_frame_id:
            self.get_logger().warn("Odometry message has empty child_frame_id")
            return

        transform = TransformStamped()

        transform.header.stamp = msg.header.stamp
        transform.header.frame_id = msg.header.frame_id
        transform.child_frame_id = msg.child_frame_id

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