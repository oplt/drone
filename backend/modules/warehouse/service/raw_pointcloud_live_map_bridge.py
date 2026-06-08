from __future__ import annotations

import asyncio
import io
import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_POINTCLOUD_TOPIC = "/warehouse/mid360/points"
DEFAULT_GLOBAL_FRAME = "odom"
DEFAULT_MAX_POINTS = 30_000
DEFAULT_MIN_PUBLISH_INTERVAL_S = 0.75


class _MemoryUpload:
    """Small async file-like wrapper compatible with live_map_storage.save_upload()."""

    content_type = "application/octet-stream"

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


def _rotation_matrix_from_quaternion_xyzw(
    x: float,
    y: float,
    z: float,
    w: float,
) -> np.ndarray:
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 1e-12:
        return np.eye(3, dtype=np.float32)

    x /= norm
    y /= norm
    z /= norm
    w /= norm

    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z

    return np.asarray(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=np.float32,
    )


def _bbox_from_xyz(xyz: np.ndarray) -> list[float]:
    mins = np.nanmin(xyz, axis=0)
    maxs = np.nanmax(xyz, axis=0)
    return [
        float(mins[0]),
        float(mins[1]),
        float(mins[2]),
        float(maxs[0]),
        float(maxs[1]),
        float(maxs[2]),
    ]


def _safe_xyz_array(raw: Any) -> np.ndarray:
    arr = np.asarray(raw)

    if arr.size == 0:
        return np.empty((0, 3), dtype=np.float32)

    if arr.dtype.fields:
        # Structured array from sensor_msgs_py.point_cloud2.read_points_numpy().
        xyz = np.column_stack(
            [
                arr["x"].astype(np.float32, copy=False),
                arr["y"].astype(np.float32, copy=False),
                arr["z"].astype(np.float32, copy=False),
            ]
        )
    else:
        xyz = arr.astype(np.float32, copy=False)
        xyz = xyz.reshape((-1, xyz.shape[-1]))[:, :3]

    finite = np.isfinite(xyz).all(axis=1)
    xyz = xyz[finite]

    return np.ascontiguousarray(xyz, dtype=np.float32)


@dataclass
class _RawPointCloudRuntime:
    node: Any
    executor: Any
    thread: threading.Thread


_runtime: _RawPointCloudRuntime | None = None
_runtime_lock = asyncio.Lock()


async def _store_and_publish_pointcloud_chunk(
    *,
    flight_id: str,
    sequence: int,
    xyz: np.ndarray,
) -> None:
    from backend.modules.warehouse.service.live_map_storage import (
        warehouse_live_map_chunk_storage,
    )
    from backend.modules.warehouse.service.live_map_stream import (
        normalize_live_map_payload,
        warehouse_live_map_stream,
    )

    if xyz.size <= 0:
        return

    payload = np.ascontiguousarray(xyz, dtype=np.float32).reshape((-1, 3)).tobytes()
    chunk_id = f"mid360_{sequence:06d}"
    bbox = _bbox_from_xyz(xyz)

    stored = await warehouse_live_map_chunk_storage.save_upload(
        flight_id=flight_id,
        chunk_id=chunk_id,
        kind="point_cloud",
        upload=_MemoryUpload(payload),
        max_bytes=32 * 1024 * 1024,
    )

    update = normalize_live_map_payload(
        {
            "flight_id": flight_id,
            "changed_chunks": [
                {
                    "id": stored.chunk_id,
                    "kind": "point_cloud",
                    "url": stored.url,
                    "content_type": stored.content_type,
                    "sequence": sequence,
                    "point_count": int(xyz.shape[0]),
                    "byte_size": stored.byte_size,
                    "checksum_sha256": stored.checksum_sha256,
                    "bbox_local_m": bbox,
                }
            ],
            "health": {
                "missing_point_cloud": False,
                "nvblox_ready": True,
                "mapping_recording": True,
                "stack_running": True,
            },
        }
    )

    await warehouse_live_map_stream.publish(update)

    logger.info(
        "Published raw point-cloud live-map chunk flight_id=%s chunk_id=%s points=%s bytes=%s",
        flight_id,
        stored.chunk_id,
        int(xyz.shape[0]),
        stored.byte_size,
    )


class _RawPointCloudLiveMapNode:
    def __init__(
        self,
        *,
        flight_id: str,
        event_loop: asyncio.AbstractEventLoop,
        topic: str,
        global_frame: str,
        max_points: int,
        min_publish_interval_s: float,
    ) -> None:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import PointCloud2
        import tf2_ros

        class NodeImpl(Node):
            pass

        self.node = NodeImpl("warehouse_raw_pointcloud_live_map_bridge")
        self.flight_id = flight_id
        self.event_loop = event_loop
        self.topic = topic
        self.global_frame = global_frame
        self.max_points = max(1, int(max_points))
        self.min_publish_interval_s = max(0.1, float(min_publish_interval_s))
        self.sequence = 0
        self.last_publish_monotonic = 0.0

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self.node)

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=3,
        )

        self.subscription = self.node.create_subscription(
            PointCloud2,
            topic,
            self._on_pointcloud,
            sensor_qos,
        )

        self.node.get_logger().info(
            f"Raw point-cloud live-map bridge subscribed topic={topic} "
            f"flight_id={flight_id} global_frame={global_frame}"
        )

    def _lookup_transform(self, msg: Any) -> Any | None:
        import rclpy
        from rclpy.duration import Duration
        from rclpy.time import Time

        source_frame = (msg.header.frame_id or "").strip()
        if not source_frame:
            return None

        if source_frame == self.global_frame:
            return None

        try:
            return self.tf_buffer.lookup_transform(
                self.global_frame,
                source_frame,
                Time.from_msg(msg.header.stamp),
                timeout=Duration(seconds=0.05),
            )
        except Exception:
            try:
                # Fallback to latest available TF. Useful during startup/sim-time jumps.
                return self.tf_buffer.lookup_transform(
                    self.global_frame,
                    source_frame,
                    rclpy.time.Time(),
                    timeout=Duration(seconds=0.05),
                )
            except Exception as exc:
                self.node.get_logger().debug(
                    f"Point-cloud TF lookup failed {self.global_frame} <- {source_frame}: {exc}"
                )
                return None

    def _transform_xyz(self, xyz: np.ndarray, transform: Any | None) -> np.ndarray:
        if transform is None:
            return xyz

        t = transform.transform.translation
        q = transform.transform.rotation

        rotation = _rotation_matrix_from_quaternion_xyzw(
            float(q.x),
            float(q.y),
            float(q.z),
            float(q.w),
        )
        translation = np.asarray([float(t.x), float(t.y), float(t.z)], dtype=np.float32)

        return np.ascontiguousarray((xyz @ rotation.T) + translation, dtype=np.float32)

    def _decode_pointcloud(self, msg: Any) -> np.ndarray:
        from sensor_msgs_py import point_cloud2

        if hasattr(point_cloud2, "read_points_numpy"):
            raw = point_cloud2.read_points_numpy(
                msg,
                field_names=("x", "y", "z"),
                skip_nans=True,
            )
            xyz = _safe_xyz_array(raw)
        else:
            raw = list(
                point_cloud2.read_points(
                    msg,
                    field_names=("x", "y", "z"),
                    skip_nans=True,
                )
            )
            xyz = _safe_xyz_array(raw)

        if xyz.shape[0] > self.max_points:
            stride = max(1, math.ceil(xyz.shape[0] / self.max_points))
            xyz = xyz[::stride]

        return np.ascontiguousarray(xyz, dtype=np.float32)

    def _on_pointcloud(self, msg: Any) -> None:
        now = time.monotonic()
        if now - self.last_publish_monotonic < self.min_publish_interval_s:
            return

        self.last_publish_monotonic = now

        try:
            xyz = self._decode_pointcloud(msg)
            if xyz.shape[0] <= 0:
                return

            transform = self._lookup_transform(msg)
            xyz = self._transform_xyz(xyz, transform)

            self.sequence += 1
            sequence = self.sequence

            asyncio.run_coroutine_threadsafe(
                _store_and_publish_pointcloud_chunk(
                    flight_id=self.flight_id,
                    sequence=sequence,
                    xyz=xyz,
                ),
                self.event_loop,
            )
        except Exception:
            self.node.get_logger().exception("Failed to publish raw point-cloud chunk")


async def start_raw_pointcloud_live_map_bridge(
    flight_id: str,
    *,
    topic: str = DEFAULT_POINTCLOUD_TOPIC,
    global_frame: str = DEFAULT_GLOBAL_FRAME,
    max_points: int = DEFAULT_MAX_POINTS,
    min_publish_interval_s: float = DEFAULT_MIN_PUBLISH_INTERVAL_S,
) -> None:
    global _runtime

    async with _runtime_lock:
        await stop_raw_pointcloud_live_map_bridge()

        import rclpy
        from rclpy.executors import SingleThreadedExecutor

        if not rclpy.ok():
            rclpy.init(args=None)

        loop = asyncio.get_running_loop()

        wrapper = _RawPointCloudLiveMapNode(
            flight_id=flight_id,
            event_loop=loop,
            topic=topic,
            global_frame=global_frame,
            max_points=max_points,
            min_publish_interval_s=min_publish_interval_s,
        )

        executor = SingleThreadedExecutor()
        executor.add_node(wrapper.node)

        thread = threading.Thread(
            target=executor.spin,
            name="warehouse-raw-pointcloud-live-map-bridge",
            daemon=True,
        )
        thread.start()

        _runtime = _RawPointCloudRuntime(
            node=wrapper.node,
            executor=executor,
            thread=thread,
        )

        logger.info(
            "Started raw point-cloud live-map bridge flight_id=%s topic=%s",
            flight_id,
            topic,
        )


async def stop_raw_pointcloud_live_map_bridge() -> None:
    global _runtime

    runtime = _runtime
    _runtime = None

    if runtime is None:
        return

    try:
        runtime.executor.shutdown()
    except Exception:
        logger.exception("Failed to shutdown raw point-cloud executor")

    try:
        runtime.node.destroy_node()
    except Exception:
        logger.exception("Failed to destroy raw point-cloud node")

    if runtime.thread.is_alive():
        runtime.thread.join(timeout=2.0)

    logger.info("Stopped raw point-cloud live-map bridge")