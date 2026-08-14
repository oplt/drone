"""Colored point-cloud live-map bridge — ROS subscriber node."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from typing import Any

import numpy as np

from backend.modules.warehouse.service.drift_guard import warehouse_transform_drift_monitor
from backend.modules.warehouse.service.map_source_config import (
    WAREHOUSE_LIVE_MAP_SOURCES,
    LiveMapSourceConfig,
)
from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker
from backend.modules.warehouse.service.pointcloud2_parser import parse_pointcloud2_msg
from backend.modules.warehouse.service.ros_message_tf import (
    resolve_pointcloud_transform,
    stamp_string_from_msg,
    transform_xyz_points,
)
from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

from .helpers import (
    _content_digest,
    _finite_xyz_rows,
    _log_future_exception,
    _store_and_publish_colored_chunk,
)
from .state import _SourceRuntime

logger = logging.getLogger(__name__)


class _ColoredPointCloudLiveMapNode:
    def __init__(
        self,
        *,
        flight_id: str,
        event_loop: asyncio.AbstractEventLoop,
        sources: dict[str, LiveMapSourceConfig],
    ) -> None:
        import tf2_ros
        from rclpy.node import Node
        from rclpy.parameter import Parameter
        from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import PointCloud2

        class NodeImpl(Node):
            pass

        self.node = NodeImpl(
            "warehouse_colored_pointcloud_live_map_bridge",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        self.flight_id = flight_id
        self.event_loop = event_loop
        self.source_runtimes = {
            source_id: _SourceRuntime(config=config) for source_id, config in sources.items()
        }
        self._warned_rgbd_without_color = False

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self.node)

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=3,
        )

        for source_id, config in sources.items():
            callback = self._make_callback(source_id)

            self.node.create_subscription(
                PointCloud2,
                config.topic,
                callback,
                sensor_qos,
            )
            self.node.get_logger().info(
                f"Colored point-cloud bridge subscribed source={source_id} "
                f"topic={config.topic} flight_id={flight_id}"
            )

    def _make_callback(self, source_id: str):
        def _callback(msg: Any) -> None:
            runtime = self.source_runtimes.get(source_id)
            if runtime is None:
                return

            topic = runtime.config.topic
            started = time.monotonic()
            with observed_span(
                "ros.callback",
                flight_id=self.flight_id,
                ros_topic=topic,
                ros_message_type=type(msg).__name__,
                frame_id=getattr(getattr(msg, "header", None), "frame_id", None),
            ):
                self._on_pointcloud(source_id, msg)
            metric_add("ros_messages", attrs={"topic": topic, "message_type": type(msg).__name__})
            metric_record(
                "ros_callback_latency",
                (time.monotonic() - started) * 1000.0,
                {"topic": topic, "message_type": type(msg).__name__},
            )
            point_step = getattr(msg, "point_step", None)
            width = getattr(msg, "width", None)
            height = getattr(msg, "height", 1)
            if point_step is not None and width is not None:
                metric_record(
                    "ros_message_size",
                    float(point_step) * float(width) * float(height or 1),
                    {"topic": topic, "message_type": type(msg).__name__},
                )

        return _callback

    def _schedule_drain(self, source_id: str) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self._drain_source(source_id),
            self.event_loop,
        )
        future.add_done_callback(_log_future_exception)

    def _on_pointcloud(self, source_id: str, msg: Any) -> None:
        runtime = self.source_runtimes.get(source_id)
        if runtime is None:
            return

        config = runtime.config
        runtime.messages_received += 1
        if runtime.messages_received == 1:
            logger.info(
                "Colored live-map subscriber received first message flight_id=%s "
                "source=%s topic=%s frame_id=%s",
                self.flight_id,
                source_id,
                config.topic,
                getattr(getattr(msg, "header", None), "frame_id", None),
            )
        now = time.monotonic()
        should_schedule = False
        should_log_backpressure = False
        dropped_frames = 0

        with runtime.lock:
            if now - runtime.last_publish_monotonic < config.min_publish_interval_s:
                return

            runtime.last_publish_monotonic = now
            if runtime.processing:
                if runtime.queued_msg is not None:
                    runtime.dropped_frames += 1
                    dropped_frames = runtime.dropped_frames
                    if now - runtime.last_backpressure_log_monotonic >= 5.0:
                        runtime.last_backpressure_log_monotonic = now
                        should_log_backpressure = True
                runtime.queued_msg = msg
                return

            runtime.queued_msg = msg
            runtime.processing = True
            should_schedule = True

        if should_log_backpressure:
            self.node.get_logger().warning(
                f"Colored point-cloud bridge falling behind source={source_id}; "
                f"dropped_stale_frames={dropped_frames}"
            )

        if should_schedule:
            self._schedule_drain(source_id)

    async def _drain_source(self, source_id: str) -> None:
        runtime = self.source_runtimes.get(source_id)
        if runtime is None:
            return

        reschedule = False
        try:
            while True:
                with runtime.lock:
                    msg = runtime.queued_msg
                    runtime.queued_msg = None
                    if msg is None:
                        runtime.processing = False
                        return

                chunk = await asyncio.to_thread(self._prepare_chunk, source_id, msg)
                if chunk is None:
                    continue
                await _store_and_publish_colored_chunk(**chunk)
        except Exception:
            logger.exception(
                "Failed to publish colored point-cloud chunk source=%s",
                source_id,
            )
        finally:
            with runtime.lock:
                if runtime.queued_msg is not None:
                    runtime.processing = True
                    reschedule = True
                else:
                    runtime.processing = False
            if reschedule:
                self._schedule_drain(source_id)

    def _prepare_chunk(self, source_id: str, msg: Any) -> dict[str, Any] | None:
        runtime = self.source_runtimes.get(source_id)
        if runtime is None:
            return None

        config = runtime.config
        started = time.monotonic()
        with observed_span(
            "mapping.pointcloud.prepare",
            flight_id=self.flight_id,
            ros_topic=config.topic,
            ros_message_type=type(msg).__name__,
            frame_id=getattr(getattr(msg, "header", None), "frame_id", None),
            **{"mapping.layer": config.layer},
        ):
            parsed = parse_pointcloud2_msg(
                msg,
                max_points=config.max_points,
                fallback_color_mode="height" if config.colored else "distance",
            )
        if parsed is None or parsed.point_count <= 0:
            logger.warning(
                "PointCloud2 parser produced no points flight_id=%s source=%s topic=%s "
                "frame_id=%s width=%s height=%s point_step=%s data_bytes=%s fields=%s",
                self.flight_id,
                source_id,
                config.topic,
                getattr(getattr(msg, "header", None), "frame_id", None),
                getattr(msg, "width", None),
                getattr(msg, "height", None),
                getattr(msg, "point_step", None),
                len(getattr(msg, "data", b"")),
                [getattr(field, "name", None) for field in getattr(msg, "fields", [])],
            )
            return None

        nvblox_status_tracker.note_message(config.topic)
        metric_add("mapping_pointclouds", attrs={"source": config.source_id, "layer": config.layer})
        if config.source_id == "rgbd_colored":
            metric_add("mapping_frames", attrs={"source": config.source_id})

        xyz = np.asarray(parsed.xyz, dtype=np.float32)
        if xyz.ndim != 2 or xyz.shape[1] != 3:
            self.node.get_logger().warning(
                f"Skipping colored live-map chunk source={source_id}: "
                f"invalid xyz shape={getattr(xyz, 'shape', None)}"
            )
            return None

        rgb = parsed.rgb
        has_rgb = bool(parsed.has_rgb and rgb is not None)
        if rgb is not None and getattr(rgb, "shape", (0,))[0] != xyz.shape[0]:
            self.node.get_logger().warning(
                f"Dropping RGB for source={source_id} because xyz/rgb lengths differ: "
                f"xyz={xyz.shape[0]} rgb={getattr(rgb, 'shape', None)}"
            )
            rgb = None
            has_rgb = False

        output_config = config
        if config.source_id == "rgbd_colored" and not has_rgb:
            output_config = replace(
                WAREHOUSE_LIVE_MAP_SOURCES["rgbd_xyz_uncolored"],
                topic=config.topic,
                global_frame=config.global_frame,
                max_points=config.max_points,
                min_publish_interval_s=config.min_publish_interval_s,
            )
            if not self._warned_rgbd_without_color:
                self.node.get_logger().warning(
                    "RGB-D PointCloud2 stream has geometry but no RGB/RGBA fields; "
                    "using RGB-D XYZ/depth cloud label instead of RGB-D Colored Cloud."
                )
                self._warned_rgbd_without_color = True

        source_frame = (getattr(getattr(msg, "header", None), "frame_id", None) or "").strip()
        if not source_frame:
            self.node.get_logger().warning(
                f"Skipping colored live-map chunk source={source_id}: empty source frame"
            )
            return None

        now_ns = int(self.node.get_clock().now().nanoseconds)
        resolved = resolve_pointcloud_transform(
            self.tf_buffer,
            msg=msg,
            global_frame=config.global_frame,
            now_ns=now_ns,
        )
        if resolved is None:
            nvblox_status_tracker.note_tf_lookup_failed()
            self.node.get_logger().warning(
                f"Skipping colored live-map chunk source={source_id}: message-stamp TF "
                f"{config.global_frame} <- {source_frame} unavailable or stale"
            )
            return None
        if resolved.needs_transform:
            warehouse_transform_drift_monitor.observe(source_id, resolved.transform)

        cloud_age_ms = resolved.message_age_ms
        transform_age_ms = resolved.transform_age_ms
        xyz = transform_xyz_points(xyz, resolved.transform)
        finite = _finite_xyz_rows(xyz)
        if not finite.any():
            metric_add("mapping_pointclouds_empty_after_filter", attrs={"source": config.source_id})
            return None
        if not finite.all():
            xyz = np.ascontiguousarray(xyz[finite], dtype=np.float32)
            if rgb is not None:
                rgb = np.ascontiguousarray(rgb[finite])
            metric_add("mapping_pointclouds_filtered", attrs={"source": config.source_id})

        if rgb is not None:
            rgb = np.ascontiguousarray(rgb)

        metric_record(
            "mapping_pointcloud_prepare_latency",
            (time.monotonic() - started) * 1000.0,
            {"topic": config.topic, "stage": "prepare"},
        )

        content_digest = _content_digest(output_config.source_id, has_rgb, xyz, rgb)
        with runtime.lock:
            if runtime.last_content_digest == content_digest:
                runtime.duplicate_chunks_skipped += 1
                return None
            runtime.last_content_digest = content_digest
            runtime.sequence += 1
            sequence = runtime.sequence

        metric_add(
            "mapping_chunks_generated",
            attrs={"source": output_config.source_id, "layer": output_config.layer},
        )
        return {
            "flight_id": self.flight_id,
            "source": output_config,
            "sequence": sequence,
            "xyz": xyz,
            "rgb": rgb,
            "has_rgb": has_rgb,
            "frame_id": config.global_frame,
            "stamp": stamp_string_from_msg(msg),
            "fields": parsed.fields,
            "cloud_age_ms": cloud_age_ms,
            "transform_age_ms": transform_age_ms,
        }


__all__ = ["_ColoredPointCloudLiveMapNode"]
