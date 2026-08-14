"""Raw point-cloud live-map bridge — ROS subscriber node."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from typing import Any

import numpy as np

from backend.modules.warehouse.service.drift_guard import warehouse_transform_drift_monitor
from backend.modules.warehouse.service.ros_message_tf import (
    resolve_pointcloud_transform,
    stamp_string_from_msg,
    transform_xyz_points,
)
from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

from .constants import DEFAULT_GLOBAL_FRAME, DEFAULT_POINTCLOUD_TOPIC
from .helpers import (
    _finite_xyz,
    _safe_xyz_array,
    _store_and_publish_pointcloud_chunk,
    _voxel_downsample,
)

logger = logging.getLogger(__name__)


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
        from rclpy.parameter import Parameter
        from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import PointCloud2

        class NodeImpl(Node):
            pass

        self.node = NodeImpl(
            "warehouse_raw_pointcloud_live_map_bridge",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
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
        self._messages_received = 0

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
            source_frame = (
                getattr(getattr(msg, "header", None), "frame_id", None) or ""
            ).strip()
            if not source_frame:
                self.node.get_logger().warning("Skipping point cloud with empty source frame")
                return None
            now_ns = int(self.node.get_clock().now().nanoseconds)
            resolved = resolve_pointcloud_transform(
                self.tf_buffer,
                msg=msg,
                global_frame=self.global_frame,
                now_ns=now_ns,
            )
            if resolved is None:
                self.node.get_logger().warning(
                    f"Skipping point cloud: message-stamp TF {self.global_frame} <- "
                    f"{source_frame} unavailable or stale"
                )
                return None
            if resolved.needs_transform:
                warehouse_transform_drift_monitor.observe("mid360_raw", resolved.transform)
            xyz = _finite_xyz(transform_xyz_points(xyz, resolved.transform))
            if xyz.shape[0] <= 0:
                return None
            with self._state_lock:
                self.sequence += 1
                sequence = self.sequence

        metric_add("ros_messages", attrs={"topic": self.topic, "message_type": type(msg).__name__})
        metric_add("mapping_pointclouds", attrs={"source": "mid360_raw", "layer": "mid360_lidar"})
        metric_add(
            "mapping_chunks_generated", attrs={"source": "mid360_raw", "layer": "mid360_lidar"}
        )
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
            "stamp": stamp_string_from_msg(msg),
            "cloud_age_ms": resolved.message_age_ms,
            "transform_age_ms": resolved.transform_age_ms,
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
        self._messages_received += 1
        if self._messages_received == 1:
            logger.info(
                "Raw live-map subscriber received first message flight_id=%s topic=%s frame_id=%s",
                self.flight_id,
                self.topic,
                getattr(getattr(msg, "header", None), "frame_id", None),
            )
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
                    logger.exception("Failed to publish raw point-cloud chunk")
        finally:
            restart = False
            with self._state_lock:
                if self._queued_msg is None:
                    self._processing = False
                else:
                    restart = True
            if restart:
                self._schedule_drain()


__all__ = ["_RawPointCloudLiveMapNode"]
