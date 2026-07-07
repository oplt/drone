from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import math
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from backend.modules.warehouse.service.drift_guard import warehouse_transform_drift_monitor
from backend.modules.warehouse.service.live_map_config import render_priority_for_source
from backend.modules.warehouse.service.map_source_config import (
    WAREHOUSE_LIVE_MAP_SOURCES,
    LiveMapSourceConfig,
    chunk_id_for_source,
)
from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker
from backend.modules.warehouse.service.pointcloud2_parser import (
    encode_xyz32,
    encode_xyzrgb32,
    parse_pointcloud2_msg,
)
from backend.modules.warehouse.service.ros_message_tf import (
    resolve_pointcloud_transform,
    stamp_string_from_msg,
    transform_xyz_points,
)
from backend.observability.instruments import observed_span, structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record
from backend.modules.warehouse.service.startup_timing_hooks import note_mapping_startup_safe

logger = logging.getLogger(__name__)

COLORED_BRIDGE_SOURCES: tuple[str, ...] = (
    "rgbd_colored",
    "nvblox_esdf",
)
_MAX_PREVIEW_POINTS = 500
_MAX_CHUNK_BYTES = 48 * 1024 * 1024


def _note_mapping_startup(mark: str) -> None:
    note_mapping_startup_safe(mark)


class _MemoryUpload:
    content_type = "application/octet-stream"

    def __init__(self, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._buffer = io.BytesIO(data)
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


def _finite_xyz_rows(xyz: np.ndarray) -> np.ndarray:
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        return np.zeros(0, dtype=bool)
    return np.isfinite(xyz).all(axis=1)


def _bbox_from_xyz(xyz: np.ndarray) -> list[float]:
    if xyz.size <= 0:
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    finite = _finite_xyz_rows(xyz)
    if not finite.any():
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    clean_xyz = xyz[finite] if not finite.all() else xyz
    mins = clean_xyz.min(axis=0)
    maxs = clean_xyz.max(axis=0)
    return [
        float(mins[0]),
        float(mins[1]),
        float(mins[2]),
        float(maxs[0]),
        float(maxs[1]),
        float(maxs[2]),
    ]


def _preview_points_m(xyz: np.ndarray, *, limit: int = _MAX_PREVIEW_POINTS) -> list[list[float]]:
    point_count = int(xyz.shape[0]) if xyz.ndim == 2 else 0
    if point_count <= 0 or limit <= 0:
        return []

    sample_count = min(limit, point_count)
    if sample_count == point_count:
        sampled = xyz
    else:
        indices = np.linspace(0, point_count - 1, sample_count, dtype=np.intp)
        sampled = xyz[indices]
    return np.round(sampled.astype(np.float64, copy=False), 3).tolist()


def _encode_pointcloud_payload(
    source: LiveMapSourceConfig,
    xyz: np.ndarray,
    rgb: np.ndarray | None,
) -> tuple[bytes, str, str, str]:
    if source.colored and rgb is not None:
        return (
            encode_xyzrgb32(xyz, rgb),
            "xyzrgb32_v1",
            "application/vnd.live-map.xyzrgb32",
            "point_cloud_rgb",
        )
    return (
        encode_xyz32(xyz),
        "xyz32_v1",
        "application/vnd.live-map.xyz32",
        "point_cloud",
    )


def _content_digest(source_id: str, has_rgb: bool, xyz: np.ndarray, rgb: np.ndarray | None) -> str:
    digest = hashlib.blake2b(digest_size=16)
    digest.update(source_id.encode("utf-8"))
    digest.update(b"1" if has_rgb else b"0")
    digest.update(np.ascontiguousarray(xyz).view(np.uint8))
    if rgb is not None:
        digest.update(np.ascontiguousarray(rgb).view(np.uint8))
    return digest.hexdigest()


def _log_future_exception(done: Any) -> None:
    try:
        exc = done.exception()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Failed to inspect colored point-cloud worker result")
        return
    if exc is not None:
        logger.error(
            "Colored point-cloud worker failed",
            exc_info=(type(exc), exc, exc.__traceback__),
        )


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
    messages_received: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass
class _ColoredBridgeRuntime:
    node: Any
    executor: Any
    thread: threading.Thread
    sources: dict[str, _SourceRuntime]


_runtime: _ColoredBridgeRuntime | None = None
_runtime_lock = asyncio.Lock()


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
    fields: tuple[str, ...] = (),
    cloud_age_ms: float | None = None,
    transform_age_ms: float | None = None,
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
            payload, encoding, content_type, storage_kind = await asyncio.to_thread(
                _encode_pointcloud_payload,
                source,
                xyz,
                rgb,
            )

            stored = await warehouse_live_map_chunk_storage.save_upload(
                flight_id=flight_id,
                chunk_id=chunk_id,
                frame_id=frame_id,
                kind=storage_kind,
                upload=_MemoryUpload(payload, content_type=content_type),
                max_bytes=_MAX_CHUNK_BYTES,
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
        "fields": list(fields),
        "source_topic": source.topic,
        "cloud_age_ms": cloud_age_ms,
        "transform_age_ms": transform_age_ms,
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
                    "preview_points_m": _preview_points_m(xyz),
                    "source": source.source_id,
                    "layer": source.layer,
                    "layer_type": source.layer,
                    "has_rgb": has_rgb,
                    "encoding": encoding,
                    "frame_id": frame_id,
                    "stamp": stamp,
                    "fields": list(fields),
                    "source_topic": source.topic,
                    "cloud_age_ms": cloud_age_ms,
                    "transform_age_ms": transform_age_ms,
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


def _runtime_busy(runtime: _ColoredBridgeRuntime) -> bool:
    for source in runtime.sources.values():
        with source.lock:
            if source.processing or source.queued_msg is not None:
                return True
    return False


def _sources_with_late_publisher_fallbacks(
    resolved_sources: dict[str, LiveMapSourceConfig],
    source_ids: tuple[str, ...],
) -> tuple[dict[str, LiveMapSourceConfig], set[str]]:
    requested_sources = set(source_ids)
    sources = {
        source_id: config
        for source_id, config in resolved_sources.items()
        if source_id in requested_sources
    }
    missing_sources = requested_sources.difference(resolved_sources)
    for source_id in missing_sources:
        configured = WAREHOUSE_LIVE_MAP_SOURCES.get(source_id)
        if configured is not None and configured.kind in {"point_cloud", "esdf"}:
            sources[source_id] = configured
    return sources, missing_sources


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

        topic_probes_list, _ = await asyncio.to_thread(probe_live_map_topic_types)
        topic_probes = {probe.topic: probe for probe in topic_probes_list}

        resolved_sources = resolve_colored_bridge_sources(topic_probes=topic_probes)
        sources, missing_sources = _sources_with_late_publisher_fallbacks(
            resolved_sources,
            source_ids,
        )
        if missing_sources:
            logger.warning(
                "Requested colored live-map sources are not publishing yet; subscribing to "
                "their configured topics so late publishers are captured: %s",
                sorted(missing_sources),
            )
        if not sources:
            logger.warning("No valid colored live-map sources requested: %s", sorted(source_ids))
            return

        from backend.infrastructure.warehouse.bridge_config import (
            configure_embedded_ros_environment,
        )

        configure_embedded_ros_environment()
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
        if not _runtime_busy(runtime):
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
        await asyncio.to_thread(runtime.executor.shutdown)
    except Exception:
        logger.exception("Failed to shutdown colored point-cloud executor")

    try:
        runtime.node.destroy_node()
    except Exception:
        logger.exception("Failed to destroy colored point-cloud node")

    if runtime.thread.is_alive():
        await asyncio.to_thread(runtime.thread.join, 2.0)

    logger.info("Stopped colored point-cloud live-map bridge")
