from __future__ import annotations

import os
from collections.abc import Iterable

from .config import source_topic_env, topic_env, topic_registry
from .ros_node_utils import configure_use_sim_time, use_sim_time_from_env


def _normalize_frame_id(frame_id: str) -> str:
    return frame_id.strip().replace("::", "/")


def _camera_offsets() -> dict[str, tuple[float, float, float]]:
    rgb_offset = (
        float(os.getenv("WAREHOUSE_RGB_CAMERA_TX", "0.20")),
        float(os.getenv("WAREHOUSE_RGB_CAMERA_TY", "0.0")),
        float(os.getenv("WAREHOUSE_RGB_CAMERA_TZ", "0.08")),
    )
    return {
        os.getenv("WAREHOUSE_RGB_CAMERA_INFO_TOPIC", "/warehouse/front/rgbd/camera_info"): (
            rgb_offset
        ),
        os.getenv(
            "WAREHOUSE_CONTRACT_RGB_CAMERA_INFO_TOPIC",
            "/warehouse/contract/rgb/camera_info",
        ): rgb_offset,
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
    from builtin_interfaces.msg import Time
    from geometry_msgs.msg import TransformStamped
    from nav_msgs.msg import Odometry
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from rclpy.qos import QoSProfile
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import CameraInfo
    from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster

    class WarehouseSimTfBroadcaster(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_sim_tf_broadcaster")
            configure_use_sim_time(self)
            self.topics = topic_env()
            registry_frames = topic_registry().frames
            self.base_link_frame = _normalize_frame_id(
                os.getenv(
                    "WAREHOUSE_BASE_LINK_FRAME",
                    registry_frames.get("base_link", "base_link"),
                )
            )
            self.odom_frame = _normalize_frame_id(
                os.getenv("WAREHOUSE_ODOM_FRAME", registry_frames.get("odom", "odom"))
            )
            self.rgbd_frame = _normalize_frame_id(
                os.getenv(
                    "WAREHOUSE_RGBD_FRAME",
                    registry_frames.get("camera", "front_rgbd_camera_link"),
                )
            )
            self.imu_frame = _normalize_frame_id(os.getenv("WAREHOUSE_IMU_FRAME", "imu_link"))
            self.lidar_frame = _normalize_frame_id(os.getenv("WAREHOUSE_LIDAR_FRAME", "lidar_link"))
            self.declare_parameter("odom_frame", self.odom_frame)
            self.declare_parameter("base_link_frame", self.base_link_frame)
            self.declare_parameter("rgbd_frame", self.rgbd_frame)
            self.declare_parameter("imu_frame", self.imu_frame)
            self.declare_parameter("lidar_frame", self.lidar_frame)
            self.declare_parameter(
                "publish_initial_identity_tf",
                os.getenv(
                    "WAREHOUSE_PUBLISH_INITIAL_IDENTITY_TF",
                    "1" if topic_registry().profile == "gazebo" else "0",
                ).lower()
                in {"1", "true", "yes", "on"},
            )
            self.declare_parameter(
                "strict_odometry_frames",
                os.getenv("WAREHOUSE_STRICT_ODOMETRY_FRAMES", "0").lower()
                in {"1", "true", "yes", "on"},
            )
            self.odom_frame = _normalize_frame_id(str(self.get_parameter("odom_frame").value))
            self.base_link_frame = _normalize_frame_id(
                str(self.get_parameter("base_link_frame").value)
            )
            self.rgbd_frame = _normalize_frame_id(str(self.get_parameter("rgbd_frame").value))
            self.imu_frame = _normalize_frame_id(str(self.get_parameter("imu_frame").value))
            self.lidar_frame = _normalize_frame_id(str(self.get_parameter("lidar_frame").value))
            self.publish_initial_identity_tf = bool(
                self.get_parameter("publish_initial_identity_tf").value
            )
            self.strict_odometry_frames = bool(self.get_parameter("strict_odometry_frames").value)
            self.camera_offsets = _camera_offsets()
            self.tf_broadcaster = TransformBroadcaster(self)
            self.static_broadcaster = StaticTransformBroadcaster(self)
            self.published_static_frames: set[str] = set()
            self._last_odom_transform: TransformStamped | None = None
            self._warned_frame_mismatches: set[tuple[str, str]] = set()
            self._sim_clock_stamp: Time | None = None
            self._waiting_for_clock_logged = False

            profile = topic_registry().profile
            source_topics = source_topic_env(profile)
            contract_odom = os.getenv(
                "WAREHOUSE_ODOM_TOPIC",
                self.topics.get("visual_slam_odom", "/warehouse/contract/odometry"),
            )
            self.declare_parameter("visual_slam_odom_topic", contract_odom)
            contract_odom = str(
                self.get_parameter("visual_slam_odom_topic").value or contract_odom
            )
            odom_qos = QoSProfile(depth=20)
            subscribed: set[str] = set()
            for topic in (
                contract_odom,
                source_topics.get("visual_slam_odom", ""),
            ):
                normalized = str(topic or "").strip()
                if not normalized or normalized in subscribed:
                    continue
                subscribed.add(normalized)
                self.create_subscription(
                    Odometry,
                    normalized,
                    self.on_odometry,
                    odom_qos,
                )
            self.create_subscription(Clock, "/clock", self._on_clock, QoSProfile(depth=10))
            self.create_timer(0.05, self._republish_odometry_tf)
            for camera_info_topic in self.camera_offsets:
                self.create_subscription(
                    CameraInfo,
                    camera_info_topic,
                    lambda message, topic=camera_info_topic: self.on_camera_info(message, topic),
                    QoSProfile(depth=10),
                )
            self._publish_default_camera_transforms()
            self._republish_odometry_tf()
            self.get_logger().info(
                f"Publishing sim TF odom={self.odom_frame} base_link={self.base_link_frame} "
                f"odom_topics={sorted(subscribed)}"
            )

        def _publish_identity_odom_tf(self) -> None:
            transform = TransformStamped()
            transform.header.stamp = self._current_stamp()
            transform.header.frame_id = self.odom_frame
            transform.child_frame_id = self.base_link_frame
            transform.transform.rotation.w = 1.0
            self.tf_broadcaster.sendTransform(transform)
            self._last_odom_transform = transform

        def _on_clock(self, message: Clock) -> None:
            first_clock = self._sim_clock_stamp is None
            self._sim_clock_stamp = message.clock
            if first_clock and self.publish_initial_identity_tf and self._last_odom_transform is None:
                self._publish_identity_odom_tf()
                self._waiting_for_clock_logged = False

        def _current_stamp(self) -> Time:
            if self._sim_clock_stamp is not None:
                return self._sim_clock_stamp
            return self.get_clock().now().to_msg()

        def _sim_time_ready(self) -> bool:
            if not use_sim_time_from_env():
                return True
            return self._sim_clock_stamp is not None

        def _publish_default_camera_transforms(self) -> None:
            defaults = {
                self.rgbd_frame: self.camera_offsets[
                    os.getenv(
                        "WAREHOUSE_RGB_CAMERA_INFO_TOPIC",
                        "/warehouse/front/rgbd/camera_info",
                    )
                ],
                os.getenv(
                    "WAREHOUSE_LEFT_CAMERA_FRAME",
                    "front_left_camera_link",
                ): self.camera_offsets[
                    os.getenv(
                        "WAREHOUSE_LEFT_CAMERA_INFO_TOPIC",
                        "/warehouse/stereo/left/camera_info",
                    )
                ],
                os.getenv(
                    "WAREHOUSE_RIGHT_CAMERA_FRAME",
                    "front_right_camera_link",
                ): self.camera_offsets[
                    os.getenv(
                        "WAREHOUSE_RIGHT_CAMERA_INFO_TOPIC",
                        "/warehouse/stereo/right/camera_info",
                    )
                ],
                self.imu_frame: (
                    float(os.getenv("WAREHOUSE_IMU_TX", "0.0")),
                    float(os.getenv("WAREHOUSE_IMU_TY", "0.0")),
                    float(os.getenv("WAREHOUSE_IMU_TZ", "0.0")),
                ),
                self.lidar_frame: (
                    float(os.getenv("WAREHOUSE_LIDAR_TX", "0.0")),
                    float(os.getenv("WAREHOUSE_LIDAR_TY", "0.0")),
                    float(os.getenv("WAREHOUSE_LIDAR_TZ", "0.05")),
                ),
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
                optical = f"{normalized}_optical"
                if optical not in self.published_static_frames:
                    transforms.append(
                        self._static_transform(
                            parent_frame=normalized,
                            child_frame=optical,
                            translation=(0.0, 0.0, 0.0),
                        )
                    )
                    self.published_static_frames.add(optical)
            if transforms:
                self.static_broadcaster.sendTransform(transforms)
                self.get_logger().info(
                    f"Published default static camera TFs under {self.base_link_frame}"
                )

        def on_odometry(self, message: Odometry) -> None:
            source_frame = _normalize_frame_id(message.header.frame_id)
            source_child = _normalize_frame_id(message.child_frame_id)
            if source_frame and source_frame != self.odom_frame:
                self._warn_frame_mismatch("odom", source_frame, self.odom_frame)
                if self.strict_odometry_frames:
                    return
            if source_child and source_child != self.base_link_frame:
                self._warn_frame_mismatch("base_link", source_child, self.base_link_frame)
                if self.strict_odometry_frames:
                    return
            # Always publish the configured base_link frame so nvblox/TF agree with Gazebo sim.
            child_frame = _normalize_frame_id(self.base_link_frame)
            transform = TransformStamped()
            transform.header.stamp = message.header.stamp
            transform.header.frame_id = self.odom_frame
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
            if not self._sim_time_ready():
                if not self._waiting_for_clock_logged:
                    self._waiting_for_clock_logged = True
                    self.get_logger().warning(
                        "Waiting for /clock before publishing odom TF "
                        "(start Gazebo with gz sim -r or press Play)"
                    )
                return
            if self._last_odom_transform is not None:
                transform = TransformStamped()
                transform.header.stamp = self._current_stamp()
                transform.header.frame_id = self._last_odom_transform.header.frame_id
                transform.child_frame_id = self._last_odom_transform.child_frame_id
                transform.transform = self._last_odom_transform.transform
                self.tf_broadcaster.sendTransform(transform)
                return
            if self.publish_initial_identity_tf:
                self._publish_identity_odom_tf()

        def _warn_frame_mismatch(self, role: str, source: str, configured: str) -> None:
            key = (role, source)
            if key in self._warned_frame_mismatches:
                return
            self._warned_frame_mismatches.add(key)
            self.get_logger().warning(
                f"Odometry {role} frame mismatch source={source} configured={configured}"
            )

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
            optical = f"{child_frame}_optical"
            if optical not in self.published_static_frames:
                self.static_broadcaster.sendTransform(
                    self._static_transform(
                        parent_frame=child_frame,
                        child_frame=optical,
                        translation=(0.0, 0.0, 0.0),
                    )
                )
                self.published_static_frames.add(optical)
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
            transform.header.stamp = self._current_stamp()
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
