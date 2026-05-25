from __future__ import annotations

import json
import os
from collections import deque

import cv2
import numpy as np

from backend.entrypoints.ros2.common import (
    DroneStateSample,
    active_mission_id,
    json_message,
    mission_spool_root,
    post_capture,
    require_ros2,
    utc_now_iso,
)
from backend.entrypoints.ros2.topics import (
    CAMERA_IMAGE_TOPIC,
    DRONE_STATE_TOPIC,
    GEOTAGGED_CAPTURE_TOPIC,
)


def _stamp_to_sec(stamp) -> float:
    return float(stamp.sec) + (float(stamp.nanosec) / 1_000_000_000.0)


def _encoding_to_image(message) -> np.ndarray:
    channels = 3 if message.encoding.lower() in {"rgb8", "bgr8"} else 1
    frame = np.frombuffer(message.data, dtype=np.uint8).reshape(
        (message.height, message.width, channels)
    )
    if message.encoding.lower() == "rgb8":
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    return frame


def main() -> None:
    require_ros2()
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from std_msgs.msg import String

    class CaptureSyncNode(Node):
        def __init__(self) -> None:
            super().__init__("capture_sync_node")
            self.capture_interval_s = max(
                0.25, float(os.getenv("IRRIGATION_CAPTURE_INTERVAL_S", "1.5"))
            )
            self.sync_tolerance_s = max(
                0.1, float(os.getenv("IRRIGATION_CAPTURE_SYNC_TOLERANCE_S", "1.0"))
            )
            self.state_buffer: deque[DroneStateSample] = deque(maxlen=60)
            self.last_capture_sec = 0.0
            self.current_mission_id: str | None = active_mission_id()
            self.publisher = self.create_publisher(String, GEOTAGGED_CAPTURE_TOPIC, 10)
            self.create_subscription(String, DRONE_STATE_TOPIC, self.on_state, 20)
            self.create_subscription(Image, CAMERA_IMAGE_TOPIC, self.on_image, 10)
            self.get_logger().info(
                f"Listening on {CAMERA_IMAGE_TOPIC} and {DRONE_STATE_TOPIC}; publishing {GEOTAGGED_CAPTURE_TOPIC}"
            )

        def on_state(self, message: String) -> None:
            try:
                payload = json.loads(message.data)
            except json.JSONDecodeError:
                return
            mission_id_value = payload.get("mission_id")
            if isinstance(mission_id_value, str) and mission_id_value.strip():
                self.current_mission_id = mission_id_value.strip()
            if payload.get("lat") is None or payload.get("lon") is None:
                return
            timestamp_value = payload.get("timestamp_utc")
            timestamp_sec = (
                float(timestamp_value)
                if isinstance(timestamp_value, (int, float))
                else self.get_clock().now().nanoseconds / 1_000_000_000.0
            )
            self.state_buffer.append(
                DroneStateSample(
                    timestamp_sec=timestamp_sec,
                    lat=float(payload["lat"]),
                    lon=float(payload["lon"]),
                    alt_m=float(payload["alt_m"]) if payload.get("alt_m") is not None else None,
                    yaw_deg=float(payload["yaw_deg"])
                    if payload.get("yaw_deg") is not None
                    else None,
                    pitch_deg=float(payload["pitch_deg"])
                    if payload.get("pitch_deg") is not None
                    else None,
                    roll_deg=float(payload["roll_deg"])
                    if payload.get("roll_deg") is not None
                    else None,
                    waypoint_seq=int(payload["waypoint_seq"])
                    if payload.get("waypoint_seq") is not None
                    else None,
                    mission_id=self.current_mission_id,
                )
            )

        def on_image(self, message: Image) -> None:
            mission_id_value = self.current_mission_id or active_mission_id()
            if not mission_id_value:
                return
            image_stamp = _stamp_to_sec(message.header.stamp)
            if image_stamp - self.last_capture_sec < self.capture_interval_s:
                return
            if not self.state_buffer:
                return
            nearest = min(self.state_buffer, key=lambda item: abs(item.timestamp_sec - image_stamp))
            if abs(nearest.timestamp_sec - image_stamp) > self.sync_tolerance_s:
                return

            frame = _encoding_to_image(message)
            mission_dir = mission_spool_root() / mission_id_value
            mission_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{int(image_stamp * 1000)}.jpg"
            image_path = mission_dir / filename
            cv2.imwrite(str(image_path), frame)
            payload = {
                "timestamp_utc": utc_now_iso(),
                "lat": nearest.lat,
                "lon": nearest.lon,
                "alt_m": nearest.alt_m,
                "yaw_deg": nearest.yaw_deg,
                "pitch_deg": nearest.pitch_deg,
                "roll_deg": nearest.roll_deg,
                "waypoint_seq": nearest.waypoint_seq,
                "meta_data": {
                    "source": "ros2_capture_sync",
                    "frame_width": int(message.width),
                    "frame_height": int(message.height),
                },
            }
            response = post_capture(
                mission_id=mission_id_value, payload=payload, image_path=image_path
            )
            self.publisher.publish(
                json_message(
                    {
                        "mission_id": mission_id_value,
                        "capture_id": response.get("id"),
                        "timestamp_utc": payload["timestamp_utc"],
                        "lat": nearest.lat,
                        "lon": nearest.lon,
                        "image_path": str(image_path),
                        "source_mission_id": nearest.mission_id,
                    }
                )
            )
            self.last_capture_sec = image_stamp

    rclpy.init()
    node = CaptureSyncNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
