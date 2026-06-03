from __future__ import annotations

import json
import os
import queue
import shutil
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import source_topic_env, topic_env, topic_registry


def _nvblox_node_running() -> bool:
    if not shutil.which("pgrep"):
        return False
    try:
        result = subprocess.run(
            ["pgrep", "-f", "[n]vblox_ros.*nvblox_node"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _field_offsets(fields: list[Any]) -> dict[str, int]:
    offsets: dict[str, int] = {}
    for field in fields:
        name = str(getattr(field, "name", ""))
        if name in {"x", "y", "z"}:
            offsets[name] = int(getattr(field, "offset", 0))
    return offsets


def pointcloud_xyz_sample(message: Any, *, max_points: int) -> list[list[float]]:
    count = int(getattr(message, "width", 0)) * int(getattr(message, "height", 0))
    point_step = int(getattr(message, "point_step", 0))
    data = bytes(getattr(message, "data", b""))
    offsets = _field_offsets(list(getattr(message, "fields", [])))
    if count <= 0 or point_step <= 0 or not data or not {"x", "y", "z"}.issubset(offsets):
        return []
    limit = min(count, max(1, max_points), len(data) // point_step)
    stride = max(1, count // limit)
    points: list[list[float]] = []
    endian = ">" if bool(getattr(message, "is_bigendian", False)) else "<"
    unpack = struct.Struct(f"{endian}f").unpack_from
    for index in range(0, count, stride):
        if len(points) >= limit:
            break
        base = index * point_step
        if base + point_step > len(data):
            break
        try:
            x = float(unpack(data, base + offsets["x"])[0])
            y = float(unpack(data, base + offsets["y"])[0])
            z = float(unpack(data, base + offsets["z"])[0])
        except (struct.error, ValueError):
            continue
        if not all(-1.0e6 < value < 1.0e6 for value in (x, y, z)):
            continue
        points.append([x, y, z])
    return points


def bbox_from_points(points: list[list[float]], fallback_pose: dict[str, float | str]) -> list[float]:
    if points:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        zs = [point[2] for point in points]
        return [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]
    x = float(fallback_pose["x_m"])
    y = float(fallback_pose["y_m"])
    z = float(fallback_pose["z_m"])
    return [x - 0.5, y - 0.5, max(0.0, z - 0.25), x + 0.5, y + 0.5, z + 0.25]


@dataclass
class BackendPublisher:
    base_url: str
    flight_id: str
    token: str
    timeout_s: float = 2.0

    def publish(self, payload: dict[str, Any]) -> tuple[bool, str]:
        if not self.base_url or not self.flight_id or not self.token:
            return False, "backend_not_configured"
        url = f"{self.base_url.rstrip('/')}/warehouse/live-map/{self.flight_id}/updates"
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        ingest_key = os.getenv("WAREHOUSE_LIVE_MAP_INGEST_TOKEN", "").strip()
        if ingest_key:
            headers["X-Warehouse-Live-Map-Ingest-Key"] = ingest_key
        elif self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            urllib.request.urlopen(req, timeout=self.timeout_s).read()
            return True, ""
        except (urllib.error.URLError, TimeoutError) as exc:
            return False, str(exc)


class AsyncBackendPublisher:
    def __init__(self, publisher: BackendPublisher, *, max_queue: int = 2) -> None:
        self.publisher = publisher
        self.queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=max(1, max_queue))
        self.lock = threading.Lock()
        self.submitted = 0
        self.dropped = 0
        self.succeeded = 0
        self.failed = 0
        self.last_error = ""
        self.last_success_monotonic: float | None = None
        self.thread = threading.Thread(target=self._run, name="warehouse-live-map-http", daemon=True)
        self.thread.start()

    def submit(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.submitted += 1
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            try:
                self.queue.get_nowait()
                with self.lock:
                    self.dropped += 1
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
            ok, error = self.publisher.publish(payload)
            with self.lock:
                if ok:
                    self.succeeded += 1
                    self.last_error = ""
                    self.last_success_monotonic = time.monotonic()
                else:
                    self.failed += 1
                    self.last_error = error

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "submitted": self.submitted,
                "dropped": self.dropped,
                "succeeded": self.succeeded,
                "failed": self.failed,
                "last_error": self.last_error,
                "last_success_monotonic": self.last_success_monotonic,
                "queue_size": self.queue.qsize(),
            }


def main() -> None:
    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import PointCloud2

    class WarehouseLiveMapPublisher(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_live_map_publisher")
            topics = topic_env()
            profile = topic_registry().profile
            source_topics = source_topic_env(profile)
            self.flight_id = os.getenv("WAREHOUSE_ACTIVE_FLIGHT_ID", "unknown")
            backend = BackendPublisher(
                base_url=os.getenv("WAREHOUSE_BACKEND_URL", "http://127.0.0.1:8000"),
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
            self.max_points_per_chunk = max(
                1,
                int(_float_env("WAREHOUSE_LIVE_MAP_MAX_POINTS_PER_CHUNK", 2048)),
            )
            self.last_publish_s = 0.0
            self.last_pointcloud_s = 0.0
            default_esdf = (
                source_topics.get("esdf")
                if profile == "gazebo"
                else topics.get("esdf", "/nvblox_node/static_esdf_pointcloud")
            )
            self.pointcloud_topic = os.getenv(
                "WAREHOUSE_ESDF_TOPIC",
                default_esdf or "/nvblox_node/static_esdf_pointcloud",
            )
            default_odom = (
                source_topics.get("visual_slam_odom")
                if profile == "gazebo"
                else topics.get("visual_slam_odom", "/warehouse/contract/odometry")
            )
            self.odom_topic = os.getenv("WAREHOUSE_ODOMETRY_TOPIC", default_odom)
            self.declare_parameter("esdf_topic", self.pointcloud_topic)
            self.declare_parameter("visual_slam_odom_topic", self.odom_topic)
            self.pointcloud_topic = str(self.get_parameter("esdf_topic").value or self.pointcloud_topic)
            self.odom_topic = str(self.get_parameter("visual_slam_odom_topic").value or self.odom_topic)
            sensor_qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
            self.create_subscription(PointCloud2, self.pointcloud_topic, self.on_pointcloud, sensor_qos)
            self.create_subscription(Odometry, self.odom_topic, self.on_odom, QoSProfile(depth=20))
            self.diagnostics_publisher = self.create_publisher(
                DiagnosticArray,
                "/warehouse/mapping/live_map_diagnostics",
                QoSProfile(depth=10),
            )
            self._last_reported_failures = 0
            self._last_heartbeat_s = 0.0
            self.create_timer(2.0, self.publish_diagnostics)

        def _live_health_flags(self, *, point_count: int = 0) -> dict[str, Any]:
            now = time.monotonic()
            nvblox_running = _nvblox_node_running()
            receiving = point_count > 0 or (
                self.last_pointcloud_s > 0.0 and (now - self.last_pointcloud_s) < 8.0
            )
            return {
                "stale_costmap": False,
                "missing_mesh": True,
                "missing_point_cloud": not receiving,
                "nvblox_ready": receiving or nvblox_running,
                "mapping_recording": receiving
                and self.flight_id not in {"", "unknown"},
                "stack_running": nvblox_running or receiving,
            }

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
            sample = pointcloud_xyz_sample(msg, max_points=self.max_points_per_chunk)
            chunk_id = f"pointcloud-{self.sequence:08d}"
            payload = {
                "type": "live_map_update",
                "flight_id": self.flight_id,
                "frame_id": msg.header.frame_id or "map",
                "pose": self.pose,
                "removed_chunk_ids": [],
                "scan_path_sample": [self.pose],
                "changed_chunks": [
                    {
                        "id": chunk_id,
                        "kind": "point_cloud",
                        "sequence": self.sequence,
                        "point_count": point_count,
                        "bbox_local_m": bbox_from_points(sample, self.pose),
                    }
                ],
                "health": self._live_health_flags(point_count=point_count),
            }
            self.publisher.submit(payload)

        def publish_diagnostics(self) -> None:
            now = time.monotonic()
            if (
                self.flight_id not in {"", "unknown"}
                and now - self._last_heartbeat_s >= self.min_period_s
            ):
                self._last_heartbeat_s = now
                self.publisher.submit(
                    {
                        "type": "live_map_update",
                        "flight_id": self.flight_id,
                        "frame_id": str(self.pose.get("frame_id") or "map"),
                        "pose": self.pose,
                        "removed_chunk_ids": [],
                        "scan_path_sample": [self.pose],
                        "changed_chunks": [],
                        "health": self._live_health_flags(point_count=0),
                    }
                )
            stats = self.publisher.snapshot()
            failures = int(stats["failed"])
            if failures > self._last_reported_failures:
                self._last_reported_failures = failures
                self.get_logger().warning(
                    f"Live map backend publish failed count={failures} error={stats['last_error']}"
                )
            diag = DiagnosticArray()
            diag.header.stamp = self.get_clock().now().to_msg()
            status = DiagnosticStatus()
            status.name = "warehouse_mapping_bridge/live_map_publisher"
            status.hardware_id = "warehouse_mapping_bridge"
            status.level = DiagnosticStatus.WARN if failures else DiagnosticStatus.OK
            status.message = "backend_errors" if failures else "ok"
            status.values = [
                KeyValue(key="submitted", value=str(stats["submitted"])),
                KeyValue(key="dropped", value=str(stats["dropped"])),
                KeyValue(key="succeeded", value=str(stats["succeeded"])),
                KeyValue(key="failed", value=str(stats["failed"])),
                KeyValue(key="last_error", value=str(stats["last_error"])),
                KeyValue(key="queue_size", value=str(stats["queue_size"])),
                KeyValue(key="payload_kind", value="pointcloud_xyz"),
                KeyValue(key="schema", value="warehouse.live_map.v1"),
            ]
            diag.status.append(status)
            self.diagnostics_publisher.publish(diag)

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
