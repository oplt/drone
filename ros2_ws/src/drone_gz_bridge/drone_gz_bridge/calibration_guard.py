import hashlib
import json
import math
from pathlib import Path

import rclpy
import yaml
from rclpy.duration import Duration
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener


class CalibrationGuard(Node):
    def __init__(self):
        super().__init__("sensor_calibration_guard")
        self.declare_parameter("calibration_file", "")
        self.declare_parameter("expected_checksum", "")
        path = Path(str(self.get_parameter("calibration_file").value))
        self.payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        transforms = self.payload["transforms"]
        transforms.sort(key=lambda item: (item["parent_frame"], item["child_frame"]))
        canonical = json.dumps(
            {"schema_version": 1, "transforms": transforms},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        actual = hashlib.sha256(canonical).hexdigest()
        expected = str(self.get_parameter("expected_checksum").value)
        if actual != expected:
            raise RuntimeError("sensor calibration checksum mismatch at launch")
        self.transforms = transforms
        self.required_runtime_frames = (
            "odom", "base_link", "lidar_link", "camera_link",
            "camera_optical_frame", "rgbd_link", "imu_link", "gimbal_link",
        )
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)
        self.deadline_ns = self.get_clock().now().nanoseconds + int(8e9)
        self.timer = self.create_timer(0.25, self._check)

    def _check(self):
        pending = []
        for expected in self.transforms:
            parent, child = expected["parent_frame"], expected["child_frame"]
            try:
                found = self.buffer.lookup_transform(parent, child, rclpy.time.Time())
            except Exception:
                pending.append(f"{parent}->{child}")
                continue
            actual_t = found.transform.translation
            actual_q = found.transform.rotation
            wanted_t, wanted_q = expected["translation"], expected["rotation"]
            error = max(
                abs(actual_t.x - wanted_t["x"]), abs(actual_t.y - wanted_t["y"]),
                abs(actual_t.z - wanted_t["z"]), abs(actual_q.x - wanted_q["x"]),
                abs(actual_q.y - wanted_q["y"]), abs(actual_q.z - wanted_q["z"]),
                abs(actual_q.w - wanted_q["w"]),
            )
            if not math.isfinite(error) or error > 1e-4:
                raise RuntimeError(f"published TF differs from calibration: {parent}->{child}")
        for child in self.required_runtime_frames:
            try:
                self.buffer.lookup_transform("warehouse_map", child, rclpy.time.Time())
            except Exception:
                pending.append(f"warehouse_map->{child}")
        if not pending:
            self.get_logger().info("Sensor calibration checksum and stable TF tree verified")
            self.timer.cancel()
        elif self.get_clock().now().nanoseconds > self.deadline_ns:
            raise RuntimeError(f"missing calibrated TF frames: {', '.join(pending)}")


def main(args=None):
    rclpy.init(args=args)
    node = CalibrationGuard()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
