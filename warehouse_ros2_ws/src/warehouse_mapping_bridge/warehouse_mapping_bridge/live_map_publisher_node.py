from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class BackendPublisher:
    base_url: str
    flight_id: str
    token: str

    def publish(self, payload: dict[str, Any]) -> None:
        if not self.base_url or not self.flight_id or not self.token:
            return
        url = f"{self.base_url.rstrip('/')}/warehouse/live-map/{self.flight_id}/updates"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            urllib.request.urlopen(req, timeout=2.0).read()
        except (urllib.error.URLError, TimeoutError):
            return


def main() -> None:
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from sensor_msgs.msg import PointCloud2

    class WarehouseLiveMapPublisher(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_live_map_publisher")
            self.flight_id = os.getenv("WAREHOUSE_ACTIVE_FLIGHT_ID", "unknown")
            self.publisher = BackendPublisher(
                base_url=os.getenv("WAREHOUSE_BACKEND_URL", "http://localhost:8000"),
                flight_id=self.flight_id,
                token=os.getenv("WAREHOUSE_BACKEND_TOKEN", ""),
            )
            self.sequence = 0
            self.pose = {"x_m": 0.0, "y_m": 0.0, "z_m": 0.0, "frame_id": "map"}
            self.min_period_s = _float_env("WAREHOUSE_LIVE_MAP_PUBLISH_PERIOD_S", 0.5)
            self.last_publish_s = 0.0
            self.pointcloud_topic = os.getenv(
                "WAREHOUSE_ESDF_TOPIC",
                "/nvblox_node/static_esdf_pointcloud",
            )
            self.odom_topic = os.getenv(
                "WAREHOUSE_ODOMETRY_TOPIC",
                "/visual_slam/tracking/odometry",
            )
            self.create_subscription(PointCloud2, self.pointcloud_topic, self.on_pointcloud, 10)
            self.create_subscription(Odometry, self.odom_topic, self.on_odom, 10)

        def on_odom(self, msg: Odometry) -> None:
            self.pose = {
                "x_m": float(msg.pose.pose.position.x),
                "y_m": float(msg.pose.pose.position.y),
                "z_m": float(msg.pose.pose.position.z),
                "frame_id": msg.header.frame_id or "map",
            }

        def on_pointcloud(self, msg: PointCloud2) -> None:
            now = time.monotonic()
            if now - self.last_publish_s < self.min_period_s:
                return
            self.last_publish_s = now
            self.sequence += 1
            point_count = int(msg.width) * int(msg.height)
            span = max(0.5, min(8.0, point_count ** (1 / 3) * 0.03))
            chunk_id = f"esdf-{self.sequence:08d}"
            payload = {
                "flight_id": self.flight_id,
                "frame_id": msg.header.frame_id or "map",
                "pose": self.pose,
                "scan_path_sample": [self.pose],
                "changed_chunks": [
                    {
                        "id": chunk_id,
                        "kind": "esdf",
                        "sequence": self.sequence,
                        "point_count": point_count,
                        "bbox_local_m": [
                            self.pose["x_m"] - span,
                            self.pose["y_m"] - span,
                            max(0.0, self.pose["z_m"] - span / 2),
                            self.pose["x_m"] + span,
                            self.pose["y_m"] + span,
                            self.pose["z_m"] + span / 2,
                        ],
                    }
                ],
                "health": {
                    "stale_costmap": False,
                    "missing_mesh": False,
                    "missing_point_cloud": False,
                    "nvblox_ready": True,
                    "mapping_recording": True,
                    "stack_running": True,
                },
            }
            self.publisher.publish(payload)

    rclpy.init()
    node = WarehouseLiveMapPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
