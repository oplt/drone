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

from backend.modules.warehouse.service.live_map_config import (
    raw_lidar_max_points,
    raw_lidar_min_publish_interval_s,
    raw_lidar_voxel_size_m,
    render_priority_for_source,
    should_persist_raw_lidar_chunks,
)
from backend.modules.warehouse.service.map_source_config import (
    WAREHOUSE_LIVE_MAP_SOURCES,
    chunk_id_for_source,
)
from backend.observability.instruments import observed_span, structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

logger = logging.getLogger(__name__)

DEFAULT_POINTCLOUD_TOPIC = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].topic
DEFAULT_GLOBAL_FRAME = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].global_frame
DEFAULT_MAX_POINTS = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].max_points
DEFAULT_MIN_PUBLISH_INTERVAL_S = WAREHOUSE_LIVE_MAP_SOURCES[
    "mid360_raw"
].min_publish_interval_s


class _MemoryUpload:
    """Small async file-like wrapper compatible with live_map_storage.save_upload()."""

    content_type = "application/octet-stream"

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


def _voxel_downsample(xyz: np.ndarray, voxel_size: float) -> np.ndarray:
    if xyz.shape[0] <= 0 or voxel_size <= 0:
        return xyz
    voxels = np.floor(xyz / voxel_size).astype(np.int64, copy=False)
    _, unique_indices = np.unique(voxels, axis=0, return_index=True)
    return np.ascontiguousarray(xyz[np.sort(unique_indices)], dtype=np.float32)


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


def _stamp_from_msg(msg: Any) -> str | None:
    header = getattr(msg, "header", None)
    stamp = getattr(header, "stamp", None) if header is not None else None
    if stamp is None:
        return None
    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if sec is None or nanosec is None:
        return None
    try:
        return f"{int(sec)}.{int(nanosec):09d}"
    except (TypeError, ValueError, OverflowError):
        return None


def _finite_xyz(xyz: np.ndarray) -> np.ndarray:
    arr = np.ascontiguousarray(xyz, dtype=np.float32).reshape((-1, 3))
    if arr.size == 0:
        return arr
    return np.ascontiguousarray(arr[np.isfinite(arr).all(axis=1)], dtype=np.float32)


def _bbox_from_xyz(xyz: np.ndarray) -> list[float]:
    clean = _finite_xyz(xyz)
    if clean.shape[0] <= 0:
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    mins = clean.min(axis=0)
    maxs = clean.max(axis=0)
    return [
        float(mins[0]),
        float(mins[1]),
        float(mins[2]),
        float(maxs[0]),
        float(maxs[1]),
        float(maxs[2]),
    ]


def _preview_points(xyz: np.ndarray, *, limit: int = 500) -> list[list[float]]:
    clean = _finite_xyz(xyz)
    if clean.shape[0] <= 0:
        return []
    stride = max(1, clean.shape[0] // max(1, limit))
    sample = clean[::stride][:limit]
    return np.round(sample.astype(np.float64, copy=False), 3).tolist()


def _safe_xyz_array(raw: Any) -> np.ndarray:
    arr = np.asarray(raw)
    if arr.size == 0:
        return np.empty((0, 3), dtype=np.float32)

    if arr.dtype.fields:
        if not all(name in arr.dtype.fields for name in ("x", "y", "z")):
            return np.empty((0, 3), dtype=np.float32)
        xyz = np.column_stack(
            [
                arr["x"].astype(np.float32, copy=False),
                arr["y"].astype(np.float32, copy=False),
                arr["z"].astype(np.float32, copy=False),
            ]
        )
    else:
        if arr.ndim == 0:
            return np.empty((0, 3), dtype=np.float32)
        xyz = arr.astype(np.float32, copy=False)
        if xyz.ndim == 1:
            if xyz.size < 3:
                return np.empty((0, 3), dtype=np.float32)
            xyz = xyz.reshape((-1, 3))
        else:
            xyz = xyz.reshape((-1, xyz.shape[-1]))
            if xyz.shape[1] < 3:
                return np.empty((0, 3), dtype=np.float32)
            xyz = xyz[:, :3]

    return _finite_xyz(xyz)


@dataclass
class _RawPointCloudRuntime:
    node: Any
    executor: Any
    thread: threading.Thread
    wrapper: Any


_runtime: _RawPointCloudRuntime | None = None
_runtime_lock = asyncio.Lock()


async def _store_and_publish_pointcloud_chunk(
    *,
    flight_id: str,
    sequence: int,
    xyz: np.ndarray,
    persist_to_disk: bool,
    stamp: str | None = None,
) -> None:
    from backend.modules.warehouse.service.live_map_storage import (
        warehouse_live_map_chunk_storage,
    )
    from backend.modules.warehouse.service.live_map_stream import (
        normalize_live_map_payload,
        warehouse_live_map_stream,
    )

    xyz = _finite_xyz(xyz)
    if xyz.size <= 0:
        return

    mid360_source = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"]
    chunk_id = chunk_id_for_source(mid360_source, sequence)
    started = time.monotonic()
    bbox = _bbox_from_xyz(xyz)
    priority = render_priority_for_source(mid360_source.source_id)
    preview_points = _preview_points(xyz)

    stored = None
    if persist_to_disk:
        payload = np.ascontiguousarray(xyz, dtype=np.float32).reshape((-1, 3)).tobytes()
        with observed_span(
            "mapping.save_chunk",
            flight_id=flight_id,
            map_id=flight_id,
            chunk_id=chunk_id,
            frame_id=mid360_source.global_frame,
            ros_topic=mid360_source.topic,
            **{
                "pointcloud.point_count": int(xyz.shape[0]),
                "mapping.layer": mid360_source.layer,
            },
        ):
            try:
                stored = await warehouse_live_map_chunk_storage.save_upload(
                    flight_id=flight_id,
                    chunk_id=chunk_id,
                    kind="point_cloud",
                    upload=_MemoryUpload(payload),
                    max_bytes=32 * 1024 * 1024,
                )
                metric_add(
                    "mapping_chunks_saved",
                    attrs={"source": mid360_source.source_id, "layer": mid360_source.layer},
                )
                metric_record(
                    "mapping_chunk_save_latency",
                    (time.monotonic() - started) * 1000.0,
                    {
                        "source": mid360_source.source_id,
                        "layer": mid360_source.layer,
                        "result": "success",
                    },
                )
            except Exception as exc:
                metric_add(
                    "mapping_chunk_save_failures",
                    attrs={"source": mid360_source.source_id, "layer": mid360_source.layer},
                )
                structured_error(
                    logger,
                    "mapping_chunk_save_failed",
                    exc,
                    flight_id=flight_id,
                    map_id=flight_id,
                    chunk_id=chunk_id,
                    ros_topic=mid360_source.topic,
                    latency_ms=(time.monotonic() - started) * 1000.0,
                )
                raise

        await asyncio.to_thread(
            warehouse_live_map_chunk_storage.save_chunk_metadata,
            flight_id=flight_id,
            chunk_id=stored.chunk_id,
            checksum_sha256=stored.checksum_sha256,
            metadata={
                "source": mid360_source.source_id,
                "layer": mid360_source.layer,
                "layer_type": mid360_source.layer,
                "kind": "point_cloud",
                "encoding": "xyz32_v1",
                "has_rgb": False,
                "sequence": sequence,
                "point_count": int(xyz.shape[0]),
                "bbox_local_m": bbox,
                "frame_id": mid360_source.global_frame,
                "content_type": stored.content_type,
                "priority": priority,
                "stamp": stamp,
            },
        )

    chunk_payload: dict[str, object] = {
        "id": stored.chunk_id if stored is not None else chunk_id,
        "kind": "point_cloud",
        "sequence": sequence,
        "point_count": int(xyz.shape[0]),
        "bbox_local_m": bbox,
        "preview_points_m": preview_points,
        "source": mid360_source.source_id,
        "layer": mid360_source.layer,
        "layer_type": mid360_source.layer,
        "has_rgb": False,
        "encoding": "xyz32_v1",
        "frame_id": mid360_source.global_frame,
        "stamp": stamp,
        "priority": priority,
    }
    if stored is not None:
        chunk_payload.update(
            {
                "url": stored.url,
                "content_type": stored.content_type,
                "byte_size": stored.byte_size,
                "checksum_sha256": stored.checksum_sha256,
            }
        )

    update = normalize_live_map_payload(
        {
            "flight_id": flight_id,
            "changed_chunks": [chunk_payload],
            "health": {
                "missing_point_cloud": False,
                "mapping_recording": True,
                "stack_running": True,
            },
        }
    )

    await warehouse_live_map_stream.publish(update)
    metric_add(
        "api_websocket_messages",
        attrs={"channel": "warehouse_live_map", "message_type": "live_map_update"},
    )

    logger.info(
        "Published raw point-cloud live-map chunk flight_id=%s chunk_id=%s points=%s persisted=%s",
        flight_id,
        stored.chunk_id if stored is not None else chunk_id,
        int(xyz.shape[0]),
        persist_to_disk,
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
        persist_to_disk: bool,
        voxel_size_m: float,
    ) -> None:
        import tf2_ros
        from rclpy.node import Node
        from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import PointCloud2

        class NodeImpl(Node):
            pass

        self.node = NodeImpl("warehouse_raw_pointcloud_live_map_bridge")
        self.flight_id = flight_id
        self.event_loop = event_loop
        self.topic = str(topic).strip() or DEFAULT_POINTCLOUD_TOPIC
        self.global_frame = str(global_frame).strip() or DEFAULT_GLOBAL_FRAME
        self.max_points = max(1, int(max_points or 1))
        self.min_publish_interval_s = max(0.1, float(min_publish_interval_s or 0.1))
        self.sequence = 0
        self.last_publish_monotonic = 0.0
        self.persist_to_disk = bool(persist_to_disk)
        self.voxel_size_m = max(0.0, float(voxel_size_m or 0.0))
        self._state_lock = threading.Lock()
        self._queued_msg: Any | None = None
        self._processing = False
        self._dropped_frames = 0
        self._last_backpressure_log_monotonic = 0.0

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self.node)

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=3,
        )

        self.subscription = self.node.create_subscription(
            PointCloud2,
            self.topic,
            self._on_pointcloud,
            sensor_qos,
        )

        self.node.get_logger().info(
            f"Raw point-cloud live-map bridge subscribed topic={self.topic} "
            f"flight_id={flight_id} global_frame={self.global_frame}"
        )

    def _lookup_transform(self, msg: Any) -> Any | None:
        import rclpy
        from rclpy.duration import Duration
        from rclpy.time import Time

        header = getattr(msg, "header", None)
        source_frame = (getattr(header, "frame_id", None) or "").strip()
        if not source_frame or source_frame == self.global_frame:
            return None

        try:
            return self.tf_buffer.lookup_transform(
                self.global_frame,
                source_frame,
                Time.from_msg(header.stamp),
                timeout=Duration(seconds=0.05),
            )
        except Exception:
            try:
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
        return _finite_xyz((xyz @ rotation.T) + translation)

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
            raw_iter = point_cloud2.read_points(
                msg,
                field_names=("x", "y", "z"),
                skip_nans=True,
            )
            xyz = _safe_xyz_array(list(raw_iter))

        if xyz.shape[0] > self.max_points:
            stride = max(1, math.ceil(xyz.shape[0] / self.max_points))
            xyz = xyz[::stride]

        if self.voxel_size_m > 0:
            xyz = _voxel_downsample(xyz, self.voxel_size_m)

        if xyz.shape[0] > self.max_points:
            stride = max(1, math.ceil(xyz.shape[0] / self.max_points))
            xyz = xyz[::stride][: self.max_points]

        return _finite_xyz(xyz)

    def _prepare_chunk(self, msg: Any) -> dict[str, Any] | None:
        started = time.monotonic()
        with observed_span(
            "ros.callback",
            flight_id=self.flight_id,
            ros_topic=self.topic,
            ros_message_type=type(msg).__name__,
            frame_id=getattr(getattr(msg, "header", None), "frame_id", None),
        ):
            xyz = self._decode_pointcloud(msg)
            if xyz.shape[0] <= 0:
                return None
            transform = self._lookup_transform(msg)
            xyz = self._transform_xyz(xyz, transform)
            if xyz.shape[0] <= 0:
                return None
            with self._state_lock:
                self.sequence += 1
                sequence = self.sequence

        metric_add("ros_messages", attrs={"topic": self.topic, "message_type": type(msg).__name__})
        metric_add("mapping_pointclouds", attrs={"source": "mid360_raw", "layer": "mid360_lidar"})
        metric_add("mapping_chunks_generated", attrs={"source": "mid360_raw", "layer": "mid360_lidar"})
        metric_record(
            "ros_callback_latency",
            (time.monotonic() - started) * 1000.0,
            {"topic": self.topic, "message_type": type(msg).__name__},
        )
        return {
            "flight_id": self.flight_id,
            "sequence": sequence,
            "xyz": xyz,
            "persist_to_disk": self.persist_to_disk,
            "stamp": _stamp_from_msg(msg),
        }

    def _schedule_drain(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self._drain_messages(), self.event_loop)

        def _done(done: Any) -> None:
            if done.cancelled():
                return
            exc = done.exception()
            if exc is not None:
                self.node.get_logger().error(f"Raw point-cloud drain failed: {exc}")

        future.add_done_callback(_done)

    def _on_pointcloud(self, msg: Any) -> None:
        now = time.monotonic()
        if now - self.last_publish_monotonic < self.min_publish_interval_s:
            return
        self.last_publish_monotonic = now

        point_step = getattr(msg, "point_step", None)
        width = getattr(msg, "width", None)
        height = getattr(msg, "height", 1)
        if point_step is not None and width is not None:
            try:
                metric_record(
                    "ros_message_size",
                    float(point_step) * float(width) * float(height or 1),
                    {"topic": self.topic, "message_type": type(msg).__name__},
                )
            except (TypeError, ValueError, OverflowError):
                pass

        with self._state_lock:
            if self._processing and self._queued_msg is not None:
                self._dropped_frames += 1
                if now - self._last_backpressure_log_monotonic >= 5.0:
                    self._last_backpressure_log_monotonic = now
                    self.node.get_logger().warning(
                        "Raw point-cloud bridge falling behind "
                        f"topic={self.topic}; dropped_stale_frames={self._dropped_frames}"
                    )
            self._queued_msg = msg
            if self._processing:
                return
            self._processing = True
        self._schedule_drain()

    async def _drain_messages(self) -> None:
        try:
            while True:
                with self._state_lock:
                    msg = self._queued_msg
                    self._queued_msg = None
                if msg is None:
                    return
                try:
                    chunk = await asyncio.to_thread(self._prepare_chunk, msg)
                    if chunk is not None:
                        await _store_and_publish_pointcloud_chunk(**chunk)
                except Exception:
                    self.node.get_logger().exception("Failed to publish raw point-cloud chunk")
        finally:
            restart = False
            with self._state_lock:
                if self._queued_msg is None:
                    self._processing = False
                else:
                    restart = True
            if restart:
                self._schedule_drain()


async def start_raw_pointcloud_live_map_bridge(
    flight_id: str,
    *,
    topic: str = DEFAULT_POINTCLOUD_TOPIC,
    global_frame: str = DEFAULT_GLOBAL_FRAME,
    max_points: int = DEFAULT_MAX_POINTS,
    min_publish_interval_s: float = DEFAULT_MIN_PUBLISH_INTERVAL_S,
    persist_to_disk: bool | None = None,
) -> None:
    global _runtime

    async with _runtime_lock:
        await stop_raw_pointcloud_live_map_bridge()

        resolved_persist = should_persist_raw_lidar_chunks() if persist_to_disk is None else bool(persist_to_disk)
        resolved_max_points = max_points if max_points != DEFAULT_MAX_POINTS else raw_lidar_max_points()
        resolved_interval = (
            min_publish_interval_s
            if min_publish_interval_s != DEFAULT_MIN_PUBLISH_INTERVAL_S
            else raw_lidar_min_publish_interval_s()
        )
        resolved_voxel = raw_lidar_voxel_size_m()

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
            max_points=resolved_max_points,
            min_publish_interval_s=resolved_interval,
            persist_to_disk=resolved_persist,
            voxel_size_m=resolved_voxel,
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
            wrapper=wrapper,
        )

        logger.info(
            "Started raw point-cloud live-map bridge flight_id=%s topic=%s max_hz=%.2f "
            "voxel_size=%.3f max_points=%s persist=%s",
            flight_id,
            topic,
            1.0 / max(0.001, float(resolved_interval)),
            resolved_voxel,
            resolved_max_points,
            resolved_persist,
        )


async def drain_raw_pointcloud_live_map_bridge(*, timeout_s: float = 5.0) -> bool:
    runtime = _runtime
    if runtime is None:
        return True
    wrapper = runtime.wrapper
    deadline = time.monotonic() + max(0.1, float(timeout_s))
    while time.monotonic() < deadline:
        with wrapper._state_lock:
            busy = wrapper._processing or wrapper._queued_msg is not None
        if not busy:
            return True
        await asyncio.sleep(0.05)
    logger.warning("Raw point-cloud bridge drain timed out after %.1fs", timeout_s)
    return False


async def stop_raw_pointcloud_live_map_bridge() -> None:
    global _runtime

    runtime = _runtime
    _runtime = None
    if runtime is None:
        return

    try:
        await asyncio.to_thread(runtime.executor.shutdown)
    except Exception:
        logger.exception("Failed to shutdown raw point-cloud executor")

    try:
        await asyncio.to_thread(runtime.node.destroy_node)
    except Exception:
        logger.exception("Failed to destroy raw point-cloud node")

    if runtime.thread.is_alive():
        await asyncio.to_thread(runtime.thread.join, 2.0)

    logger.info("Stopped raw point-cloud live-map bridge")
