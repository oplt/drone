from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import topic_env


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
    timeout_s: float = 2.0

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
            urllib.request.urlopen(req, timeout=self.timeout_s).read()
        except (urllib.error.URLError, TimeoutError):
            return


class AsyncBackendPublisher:
    def __init__(self, publisher: BackendPublisher, *, max_queue: int = 2) -> None:
        self.publisher = publisher
        self.queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=max(1, max_queue))
        self.thread = threading.Thread(target=self._run, name="warehouse-live-map-http", daemon=True)
        self.thread.start()

    def submit(self, payload: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            self.queue.put_nowait(payload)

    def close(self) -> None:
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass

    def _run(self) -> None:
        while True:
            payload = self.queue.get()
            if payload is None:
                return
            self.publisher.publish(payload)


def main() -> None:
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import PointCloud2

    class WarehouseLiveMapPublisher(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_live_map_publisher")
            topics = topic_env()
            self.flight_id = os.getenv("WAREHOUSE_ACTIVE_FLIGHT_ID", "unknown")
            backend = BackendPublisher(
                base_url=os.getenv("WAREHOUSE_BACKEND_URL", ""),
                flight_id=self.flight_id,
                token=os.getenv("WAREHOUSE_BACKEND_TOKEN", ""),
                timeout_s=max(0.1, _float_env("WAREHOUSE_LIVE_MAP_HTTP_TIMEOUT_S", 1.0)),
            )
            self.publisher = AsyncBackendPublisher(
                backend,
                max_queue=int(_float_env("WAREHOUSE_LIVE_MAP_QUEUE_SIZE", 2)),
            )
            self.sequence = 0
            self.pose = {"x_m": 0.0, "y_m": 0.0, "z_m": 0.0, "frame_id": "map"}
            self.min_period_s = _float_env("WAREHOUSE_LIVE_MAP_PUBLISH_PERIOD_S", 0.5)
            self.last_publish_s = 0.0
            self.last_pointcloud_s = 0.0
            self.pointcloud_topic = os.getenv("WAREHOUSE_ESDF_TOPIC", topics["esdf"])
            self.odom_topic = os.getenv("WAREHOUSE_ODOMETRY_TOPIC", topics["visual_slam_odom"])
            self.declare_parameter("esdf_topic", self.pointcloud_topic)
            self.declare_parameter("visual_slam_odom_topic", self.odom_topic)
            self.pointcloud_topic = str(self.get_parameter("esdf_topic").value or self.pointcloud_topic)
            self.odom_topic = str(self.get_parameter("visual_slam_odom_topic").value or self.odom_topic)
            sensor_qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
            self.create_subscription(PointCloud2, self.pointcloud_topic, self.on_pointcloud, sensor_qos)
            self.create_subscription(Odometry, self.odom_topic, self.on_odom, QoSProfile(depth=20))

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
            self.last_pointcloud_s = now
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
                    "nvblox_ready": point_count > 0,
                    "mapping_recording": self.flight_id not in {"", "unknown"},
                    "stack_running": point_count > 0,
                },
            }
            self.publisher.submit(payload)

    rclpy.init()
    node = WarehouseLiveMapPublisher()
    try:
        rclpy.spin(node)
    finally:
        if hasattr(node, "publisher"):
            node.publisher.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
