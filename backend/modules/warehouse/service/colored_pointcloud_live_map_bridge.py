from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.modules.warehouse.service.live_map_config import render_priority_for_source
from backend.modules.warehouse.service.map_source_config import (
    LiveMapSourceConfig,
    chunk_id_for_source,
)
from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker
from backend.modules.warehouse.service.pointcloud2_parser import (
    encode_xyz32,
    encode_xyzrgb32,
    parse_pointcloud2_msg,
)
from backend.observability.instruments import observed_span, structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

logger = logging.getLogger(__name__)

COLORED_BRIDGE_SOURCES: tuple[str, ...] = (
    "rgbd_colored",
    "nvblox_esdf",
)


def _note_mapping_startup(mark: str) -> None:
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            note_mapping_startup,
        )

        note_mapping_startup(mark)
    except ModuleNotFoundError as exc:
        logger.warning("Optional mapping startup timing unavailable: %s", exc)


class _MemoryUpload:
    content_type = "application/octet-stream"

    def __init__(self, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._buffer = io.BytesIO(data)
        self.content_type = content_type

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


@dataclass
class _SourceRuntime:
    config: LiveMapSourceConfig
    sequence: int = 0
    last_publish_monotonic: float = 0.0
    queued_msg: Any | None = None
    processing: bool = False
    dropped_frames: int = 0
    last_backpressure_log_monotonic: float = 0.0
    last_content_digest: str | None = None
    duplicate_chunks_skipped: int = 0


@dataclass
class _ColoredBridgeRuntime:
    node: Any
    executor: Any
    thread: threading.Thread
    sources: dict[str, _SourceRuntime]


_runtime: _ColoredBridgeRuntime | None = None
_runtime_lock = asyncio.Lock()


def _stamp_from_msg(msg: Any) -> str | None:
    header = getattr(msg, "header", None)
    stamp = getattr(header, "stamp", None) if header is not None else None
    if stamp is None:
        return None
    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if sec is None or nanosec is None:
        return None
    return f"{int(sec)}.{int(nanosec):09d}"


async def _store_and_publish_colored_chunk(
    *,
    flight_id: str,
    source: LiveMapSourceConfig,
    sequence: int,
    xyz: np.ndarray,
    rgb: np.ndarray | None,
    has_rgb: bool,
    frame_id: str,
    stamp: str | None = None,
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

    chunk_id = chunk_id_for_source(source, sequence)
    bbox = _bbox_from_xyz(xyz)
    started = time.monotonic()

    with observed_span(
        "mapping.save_chunk",
        flight_id=flight_id,
        map_id=flight_id,
        chunk_id=chunk_id,
        frame_id=frame_id,
        ros_topic=source.topic,
        **{
            "pointcloud.point_count": int(xyz.shape[0]),
            "mapping.layer": source.layer,
        },
    ):
        try:
            if source.colored and rgb is not None:
                payload = encode_xyzrgb32(xyz, rgb)
                encoding = "xyzrgb32_v1"
                content_type = "application/vnd.live-map.xyzrgb32"
                storage_kind = "point_cloud_rgb"
            else:
                payload = encode_xyz32(xyz)
                encoding = "xyz32_v1"
                content_type = "application/vnd.live-map.xyz32"
                storage_kind = "point_cloud"

            stored = await warehouse_live_map_chunk_storage.save_upload(
                flight_id=flight_id,
                chunk_id=chunk_id,
                kind=storage_kind,
                upload=_MemoryUpload(payload, content_type=content_type),
                max_bytes=48 * 1024 * 1024,
            )
            metric_add(
                "mapping_chunks_saved",
                attrs={"source": source.source_id, "layer": source.layer},
            )
            metric_record(
                "mapping_chunk_save_latency",
                (time.monotonic() - started) * 1000.0,
                {"source": source.source_id, "layer": source.layer, "result": "success"},
            )
        except Exception as exc:
            metric_add(
                "mapping_chunk_save_failures",
                attrs={"source": source.source_id, "layer": source.layer},
            )
            structured_error(
                logger,
                "mapping_chunk_save_failed",
                exc,
                flight_id=flight_id,
                map_id=flight_id,
                chunk_id=chunk_id,
                ros_topic=source.topic,
                latency_ms=(time.monotonic() - started) * 1000.0,
            )
            raise

    priority = render_priority_for_source(source.source_id)
    sidecar_metadata = {
            "source": source.source_id,
            "layer": source.layer,
            "layer_type": source.layer,
            "kind": source.kind,
            "encoding": encoding,
            "has_rgb": has_rgb,
            "sequence": sequence,
            "point_count": int(xyz.shape[0]),
            "bbox_local_m": bbox,
            "frame_id": frame_id,
            "content_type": content_type,
            "priority": priority,
            "stamp": stamp,
        }
    await asyncio.to_thread(
        warehouse_live_map_chunk_storage.save_chunk_metadata,
        flight_id=flight_id,
        chunk_id=stored.chunk_id,
        checksum_sha256=stored.checksum_sha256,
        metadata=sidecar_metadata,
    )

    logger.info(
        "live_map_chunk_written flight_id=%s source=%s chunk_id=%s point_count=%s "
        "file_path=%s file_size=%s sequence_number=%s",
        flight_id,
        source.source_id,
        stored.chunk_id,
        int(xyz.shape[0]),
        stored.path,
        stored.byte_size,
        sequence,
    )

    preview_stride = max(1, xyz.shape[0] // 500)
    preview_points = [
        [round(float(x), 3), round(float(y), 3), round(float(z), 3)]
        for x, y, z in xyz[::preview_stride][:500]
    ]

    update = normalize_live_map_payload(
        {
            "flight_id": flight_id,
            "frame_id": frame_id,
            "changed_chunks": [
                {
                    "id": stored.chunk_id,
                    "kind": source.kind,
                    "url": stored.url,
                    "content_type": stored.content_type,
                    "sequence": sequence,
                    "point_count": int(xyz.shape[0]),
                    "byte_size": stored.byte_size,
                    "checksum_sha256": stored.checksum_sha256,
                    "bbox_local_m": bbox,
                    "preview_points_m": preview_points,
                    "source": source.source_id,
                    "layer": source.layer,
                    "layer_type": source.layer,
                    "has_rgb": has_rgb,
                    "encoding": encoding,
                    "frame_id": frame_id,
                    "stamp": stamp,
                    "priority": priority,
                }
            ],
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

    if source.source_id == "rgbd_colored" and sequence == 1:
        _note_mapping_startup("first_rgbd_chunk_monotonic")

    logger.info(
        "Published colored live-map chunk flight_id=%s source=%s chunk_id=%s points=%s has_rgb=%s",
        flight_id,
        source.source_id,
        stored.chunk_id,
        int(xyz.shape[0]),
        has_rgb,
    )


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
        from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import PointCloud2

        class NodeImpl(Node):
            pass

        self.node = NodeImpl("warehouse_colored_pointcloud_live_map_bridge")
        self.flight_id = flight_id
        self.event_loop = event_loop
        self.source_runtimes = {
            source_id: _SourceRuntime(config=config)
            for source_id, config in sources.items()
        }

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
            topic = self.source_runtimes[source_id].config.topic
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

    def _lookup_transform(self, msg: Any, global_frame: str) -> Any | None:
        import rclpy
        from rclpy.duration import Duration
        from rclpy.time import Time

        source_frame = (msg.header.frame_id or "").strip()
        if not source_frame or source_frame == global_frame:
            return None

        try:
            return self.tf_buffer.lookup_transform(
                global_frame,
                source_frame,
                Time.from_msg(msg.header.stamp),
                timeout=Duration(seconds=0.05),
            )
        except Exception:
            try:
                return self.tf_buffer.lookup_transform(
                    global_frame,
                    source_frame,
                    rclpy.time.Time(),
                    timeout=Duration(seconds=0.05),
                )
            except Exception as exc:
                self.node.get_logger().debug(
                    f"TF lookup failed {global_frame} <- {source_frame}: {exc}"
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

    def _on_pointcloud(self, source_id: str, msg: Any) -> None:
        runtime = self.source_runtimes.get(source_id)
        if runtime is None:
            return

        config = runtime.config
        now = time.monotonic()
        if now - runtime.last_publish_monotonic < config.min_publish_interval_s:
            return

        runtime.last_publish_monotonic = now
        if runtime.processing and runtime.queued_msg is not None:
            runtime.dropped_frames += 1
            if now - runtime.last_backpressure_log_monotonic >= 5.0:
                runtime.last_backpressure_log_monotonic = now
                self.node.get_logger().warning(
                    f"Colored point-cloud bridge falling behind source={source_id}; "
                    f"dropped_stale_frames={runtime.dropped_frames}"
                )
        runtime.queued_msg = msg
        if runtime.processing:
            return

        runtime.processing = True
        future = asyncio.run_coroutine_threadsafe(
            self._drain_source(source_id),
            self.event_loop,
        )
        future.add_done_callback(
            lambda done: done.exception() if not done.cancelled() else None
        )

    async def _drain_source(self, source_id: str) -> None:
        runtime = self.source_runtimes.get(source_id)
        if runtime is None:
            return

        try:
            while True:
                msg = runtime.queued_msg
                runtime.queued_msg = None
                if msg is None:
                    return
                chunk = await asyncio.to_thread(self._prepare_chunk, source_id, msg)
                if chunk is None:
                    continue
                await _store_and_publish_colored_chunk(**chunk)
        except Exception:
            self.node.get_logger().exception(
                "Failed to publish colored point-cloud chunk source=%s",
                source_id,
            )
        finally:
            runtime.processing = False
            if runtime.queued_msg is not None:
                runtime.processing = True
                future = asyncio.run_coroutine_threadsafe(
                    self._drain_source(source_id),
                    self.event_loop,
                )
                future.add_done_callback(
                    lambda done: done.exception() if not done.cancelled() else None
                )

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
            return None

        nvblox_status_tracker.note_message(config.topic)
        metric_add("mapping_pointclouds", attrs={"source": config.source_id, "layer": config.layer})
        if config.source_id == "rgbd_colored":
            metric_add("mapping_frames", attrs={"source": config.source_id})

        xyz = parsed.xyz
        source_frame = (getattr(getattr(msg, "header", None), "frame_id", None) or "").strip()
        transform = self._lookup_transform(msg, config.global_frame)
        if source_frame and source_frame != config.global_frame:
            if transform is None:
                self.node.get_logger().warning(
                    "Skipping colored live-map chunk source=%s: TF %s <- %s unavailable",
                    source_id,
                    config.global_frame,
                    source_frame,
                )
                return None
        xyz = self._transform_xyz(xyz, transform)
        metric_record(
            "ros_callback_latency",
            (time.monotonic() - started) * 1000.0,
            {"topic": config.topic, "stage": "prepare"},
        )

        digest = hashlib.sha1()
        digest.update(config.source_id.encode("utf-8"))
        digest.update(str(parsed.has_rgb).encode("ascii"))
        digest.update(np.ascontiguousarray(xyz).view(np.uint8))
        if parsed.rgb is not None:
            digest.update(np.ascontiguousarray(parsed.rgb).view(np.uint8))
        content_digest = digest.hexdigest()
        if runtime.last_content_digest == content_digest:
            runtime.duplicate_chunks_skipped += 1
            return None
        runtime.last_content_digest = content_digest

        runtime.sequence += 1
        metric_add(
            "mapping_chunks_generated",
            attrs={"source": config.source_id, "layer": config.layer},
        )
        return {
            "flight_id": self.flight_id,
            "source": config,
            "sequence": runtime.sequence,
            "xyz": xyz,
            "rgb": parsed.rgb,
            "has_rgb": parsed.has_rgb,
            "frame_id": config.global_frame,
            "stamp": _stamp_from_msg(msg),
        }


async def start_colored_pointcloud_live_map_bridge(
    flight_id: str,
    *,
    source_ids: tuple[str, ...] = COLORED_BRIDGE_SOURCES,
) -> None:
    global _runtime

    async with _runtime_lock:
        await stop_colored_pointcloud_live_map_bridge()

        from backend.modules.warehouse.service.live_map_readiness import (
            probe_live_map_topic_types,
            resolve_colored_bridge_sources,
        )

        topic_probes_list, _ = probe_live_map_topic_types()
        topic_probes = {probe.topic: probe for probe in topic_probes_list}

        sources = resolve_colored_bridge_sources(topic_probes=topic_probes)
        if not sources:
            logger.warning("No colored live-map PointCloud2 sources resolved")
            return

        import rclpy
        from rclpy.executors import SingleThreadedExecutor

        if not rclpy.ok():
            rclpy.init(args=None)

        loop = asyncio.get_running_loop()
        wrapper = _ColoredPointCloudLiveMapNode(
            flight_id=flight_id,
            event_loop=loop,
            sources=sources,
        )

        executor = SingleThreadedExecutor()
        executor.add_node(wrapper.node)

        thread = threading.Thread(
            target=executor.spin,
            name="warehouse-colored-pointcloud-live-map-bridge",
            daemon=True,
        )
        thread.start()

        _runtime = _ColoredBridgeRuntime(
            node=wrapper.node,
            executor=executor,
            thread=thread,
            sources=wrapper.source_runtimes,
        )

        _note_mapping_startup("bridge_start_monotonic")

        logger.info(
            "Started colored point-cloud live-map bridge flight_id=%s sources=%s",
            flight_id,
            list(sources.keys()),
        )


async def drain_colored_pointcloud_live_map_bridge(*, timeout_s: float = 5.0) -> bool:
    """Wait for in-flight colored point-cloud chunks to finish publishing."""
    runtime = _runtime
    if runtime is None:
        return True

    deadline = time.monotonic() + max(0.1, timeout_s)
    while time.monotonic() < deadline:
        busy = any(
            source.processing or source.queued_msg is not None
            for source in runtime.sources.values()
        )
        if not busy:
            logger.info(
                "Colored point-cloud bridge drained sources=%s",
                list(runtime.sources.keys()),
            )
            return True
        await asyncio.sleep(0.05)

    logger.warning(
        "Colored point-cloud bridge drain timed out after %.1fs sources=%s",
        timeout_s,
        list(runtime.sources.keys()),
    )
    return False


async def stop_colored_pointcloud_live_map_bridge() -> None:
    global _runtime

    runtime = _runtime
    _runtime = None

    if runtime is None:
        return

    try:
        runtime.executor.shutdown()
    except Exception:
        logger.exception("Failed to shutdown colored point-cloud executor")

    try:
        runtime.node.destroy_node()
    except Exception:
        logger.exception("Failed to destroy colored point-cloud node")

    if runtime.thread.is_alive():
        runtime.thread.join(timeout=2.0)

    logger.info("Stopped colored point-cloud live-map bridge")
