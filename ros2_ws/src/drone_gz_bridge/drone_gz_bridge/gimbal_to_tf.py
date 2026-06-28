import math

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster


class GimbalToTf(Node):
    """Single owner for the dynamic base_link -> gimbal_link transform."""

    def __init__(self):
        super().__init__("gimbal_to_tf")
        self.declare_parameter("joint_state_topic", "/joint_states")
        self.declare_parameter("roll_joint", "gimbal_roll_joint")
        self.declare_parameter("pitch_joint", "gimbal_pitch_joint")
        self.declare_parameter("yaw_joint", "gimbal_yaw_joint")
        self.declare_parameter("translation_xyz", [0.0, 0.0, -0.02])
        self._angles = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self._joint_names = {
            axis: str(self.get_parameter(f"{axis}_joint").value) for axis in self._angles
        }
        self._translation = [float(value) for value in self.get_parameter("translation_xyz").value]
        self._broadcaster = TransformBroadcaster(self)
        self.create_subscription(
            JointState,
            str(self.get_parameter("joint_state_topic").value),
            self._joint_state,
            10,
        )
        self.create_timer(0.05, self._publish)

    def _joint_state(self, message: JointState) -> None:
        positions = dict(zip(message.name, message.position, strict=False))
        for axis, joint_name in self._joint_names.items():
            if joint_name in positions and math.isfinite(positions[joint_name]):
                self._angles[axis] = float(positions[joint_name])

    def _publish(self) -> None:
        roll, pitch, yaw = (self._angles[axis] for axis in ("roll", "pitch", "yaw"))
        cr, sr = math.cos(roll / 2), math.sin(roll / 2)
        cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = "base_link"
        transform.child_frame_id = "gimbal_link"
        transform.transform.translation.x = self._translation[0]
        transform.transform.translation.y = self._translation[1]
        transform.transform.translation.z = self._translation[2]
        transform.transform.rotation.x = sr * cp * cy - cr * sp * sy
        transform.transform.rotation.y = cr * sp * cy + sr * cp * sy
        transform.transform.rotation.z = cr * cp * sy - sr * sp * cy
        transform.transform.rotation.w = cr * cp * cy + sr * sp * sy
        self._broadcaster.sendTransform(transform)


def main(args=None):
    rclpy.init(args=args)
    node = GimbalToTf()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
