from __future__ import annotations

import os
from collections.abc import Iterable

from .config import topic_env


def _normalize_frame_id(frame_id: str) -> str:
    return frame_id.strip().replace("::", "/")


def _camera_offsets() -> dict[str, tuple[float, float, float]]:
    return {
        os.getenv("WAREHOUSE_RGB_CAMERA_INFO_TOPIC", "/warehouse/front/rgbd/camera_info"): (
            float(os.getenv("WAREHOUSE_RGB_CAMERA_TX", "0.20")),
            float(os.getenv("WAREHOUSE_RGB_CAMERA_TY", "0.0")),
            float(os.getenv("WAREHOUSE_RGB_CAMERA_TZ", "0.08")),
        ),
        os.getenv("WAREHOUSE_LEFT_CAMERA_INFO_TOPIC", "/warehouse/stereo/left/camera_info"): (
            float(os.getenv("WAREHOUSE_LEFT_CAMERA_TX", "0.20")),
            float(os.getenv("WAREHOUSE_LEFT_CAMERA_TY", "0.04")),
            float(os.getenv("WAREHOUSE_LEFT_CAMERA_TZ", "0.09")),
        ),
        os.getenv("WAREHOUSE_RIGHT_CAMERA_INFO_TOPIC", "/warehouse/stereo/right/camera_info"): (
            float(os.getenv("WAREHOUSE_RIGHT_CAMERA_TX", "0.20")),
            float(os.getenv("WAREHOUSE_RIGHT_CAMERA_TY", "-0.04")),
            float(os.getenv("WAREHOUSE_RIGHT_CAMERA_TZ", "0.09")),
        ),
    }


def main() -> None:
    import rclpy
    from geometry_msgs.msg import TransformStamped
    from nav_msgs.msg import Odometry
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from sensor_msgs.msg import CameraInfo
    from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster

    class WarehouseSimTfBroadcaster(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_sim_tf_broadcaster")
            self.topics = topic_env()
            self.base_link_frame = os.getenv("WAREHOUSE_BASE_LINK_FRAME", "base_link")
            self.odom_frame = os.getenv("WAREHOUSE_ODOM_FRAME", "odom")
            self.camera_offsets = _camera_offsets()
            self.tf_broadcaster = TransformBroadcaster(self)
            self.static_broadcaster = StaticTransformBroadcaster(self)
            self.published_static_frames: set[str] = set()
            self._last_odom_transform: TransformStamped | None = None

            odom_topic = os.getenv(
                "WAREHOUSE_ODOM_TOPIC",
                self.topics["visual_slam_odom"],
            )
            self.create_subscription(Odometry, odom_topic, self.on_odometry, 20)
            self.create_timer(0.05, self._republish_odometry_tf)
            for camera_info_topic in self.camera_offsets:
                self.create_subscription(
                    CameraInfo,
                    camera_info_topic,
                    lambda message, topic=camera_info_topic: self.on_camera_info(message, topic),
                    10,
                )
            self._publish_default_camera_transforms()
            self._republish_odometry_tf()
            self.get_logger().info(
                f"Publishing sim TF odom={self.odom_frame} base_link={self.base_link_frame} "
                f"odom_topic={odom_topic}"
            )

        def _publish_default_camera_transforms(self) -> None:
            defaults = {
                os.getenv("WAREHOUSE_RGBD_FRAME", "front_rgbd_camera_link"): self.camera_offsets[
                    os.getenv("WAREHOUSE_RGB_CAMERA_INFO_TOPIC", "/warehouse/front/rgbd/camera_info")
                ],
                os.getenv("WAREHOUSE_LEFT_CAMERA_FRAME", "front_left_camera_link"): self.camera_offsets[
                    os.getenv("WAREHOUSE_LEFT_CAMERA_INFO_TOPIC", "/warehouse/stereo/left/camera_info")
                ],
                os.getenv("WAREHOUSE_RIGHT_CAMERA_FRAME", "front_right_camera_link"): self.camera_offsets[
                    os.getenv("WAREHOUSE_RIGHT_CAMERA_INFO_TOPIC", "/warehouse/stereo/right/camera_info")
                ],
            }
            transforms: list[TransformStamped] = []
            for child_frame, offset in defaults.items():
                normalized = _normalize_frame_id(child_frame)
                if normalized in self.published_static_frames:
                    continue
                transforms.append(
                    self._static_transform(
                        parent_frame=self.base_link_frame,
                        child_frame=normalized,
                        translation=offset,
                    )
                )
                self.published_static_frames.add(normalized)
            if transforms:
                self.static_broadcaster.sendTransform(transforms)
                self.get_logger().info(
                    f"Published default static camera TFs under {self.base_link_frame}"
                )

        def on_odometry(self, message: Odometry) -> None:
            # Always publish the configured base_link frame so nvblox/TF agree with Gazebo sim.
            child_frame = _normalize_frame_id(self.base_link_frame)
            transform = TransformStamped()
            transform.header.stamp = self.get_clock().now().to_msg()
            transform.header.frame_id = _normalize_frame_id(message.header.frame_id or self.odom_frame)
            transform.child_frame_id = child_frame

            # Odometry.pose.pose is geometry_msgs/Pose, but TransformStamped.transform
            # must be geometry_msgs/Transform. Copy the compatible fields explicitly.
            transform.transform.translation.x = float(message.pose.pose.position.x)
            transform.transform.translation.y = float(message.pose.pose.position.y)
            transform.transform.translation.z = float(message.pose.pose.position.z)
            transform.transform.rotation.x = float(message.pose.pose.orientation.x)
            transform.transform.rotation.y = float(message.pose.pose.orientation.y)
            transform.transform.rotation.z = float(message.pose.pose.orientation.z)
            transform.transform.rotation.w = float(message.pose.pose.orientation.w)

            self._last_odom_transform = transform
            self.tf_broadcaster.sendTransform(transform)

        def _republish_odometry_tf(self) -> None:
            if self._last_odom_transform is not None:
                transform = TransformStamped()
                transform.header.stamp = self.get_clock().now().to_msg()
                transform.header.frame_id = self._last_odom_transform.header.frame_id
                transform.child_frame_id = self._last_odom_transform.child_frame_id
                transform.transform = self._last_odom_transform.transform
                self.tf_broadcaster.sendTransform(transform)
                return
            transform = TransformStamped()
            transform.header.stamp = self.get_clock().now().to_msg()
            transform.header.frame_id = self.odom_frame
            transform.child_frame_id = self.base_link_frame
            transform.transform.rotation.w = 1.0
            self.tf_broadcaster.sendTransform(transform)

        def on_camera_info(self, message: CameraInfo, topic: str) -> None:
            child_frame = _normalize_frame_id(message.header.frame_id)
            if not child_frame or child_frame in self.published_static_frames:
                return
            parent_frame = (
                self._last_odom_transform.child_frame_id
                if self._last_odom_transform is not None
                else self.base_link_frame
            )
            offset = self.camera_offsets.get(topic, (0.0, 0.0, 0.0))
            transform = self._static_transform(
                parent_frame=parent_frame,
                child_frame=child_frame,
                translation=offset,
            )
            self.static_broadcaster.sendTransform(transform)
            self.published_static_frames.add(child_frame)
            self.get_logger().info(
                f"Published static TF {self.base_link_frame} -> {child_frame} from {topic}"
            )

        def _static_transform(
                self,
                *,
                parent_frame: str,
                child_frame: str,
                translation: Iterable[float],
        ) -> TransformStamped:
            tx, ty, tz = translation
            transform = TransformStamped()
            transform.header.stamp = self.get_clock().now().to_msg()
            transform.header.frame_id = parent_frame
            transform.child_frame_id = child_frame
            transform.transform.translation.x = float(tx)
            transform.transform.translation.y = float(ty)
            transform.transform.translation.z = float(tz)
            if child_frame.endswith("_optical"):
                # REP-103 camera optical frame relative to camera link.
                transform.transform.rotation.x = -0.5
                transform.transform.rotation.y = 0.5
                transform.transform.rotation.z = -0.5
                transform.transform.rotation.w = 0.5
            else:
                transform.transform.rotation.w = 1.0
            return transform

    rclpy.init()
    node = WarehouseSimTfBroadcaster()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()