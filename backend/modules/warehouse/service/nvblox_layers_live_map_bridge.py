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

from backend.modules.warehouse.service.live_map_config import render_priority_for_source
from backend.modules.warehouse.service.map_source_config import (
    OCCUPANCY_TOPIC_CANDIDATES,
    WAREHOUSE_LIVE_MAP_SOURCES,
    LiveMapSourceConfig,
    chunk_id_for_source,
)
from backend.modules.warehouse.service.nvblox_mesh_adapter import parse_nvblox_mesh_message
from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker
from backend.modules.warehouse.service.nvblox_voxel_layer_parser import (
    parse_voxel_block_layer_msg,
)
from backend.modules.warehouse.service.occupancy_grid_parser import (
    encode_occupancy_grid,
    parse_occupancy_grid_msg,
)
from backend.modules.warehouse.service.occupancy_live_map_chunk import (
    store_and_publish_occupancy_chunk,
)
from backend.modules.warehouse.service.pointcloud2_parser import encode_xyz32, encode_xyzrgb32

logger = logging.getLogger(__name__)


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
    """Return a finite bbox; invalid/all-NaN clouds become a harmless zero bbox."""
    if xyz.size <= 0:
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    arr = np.asarray(xyz, dtype=np.float32).reshape((-1, 3))
    finite = np.isfinite(arr).all(axis=1)
    if not bool(finite.any()):
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    valid = arr[finite]
    mins = valid.min(axis=0)
    maxs = valid.max(axis=0)
    return [
        float(mins[0]),
        float(mins[1]),
        float(mins[2]),
        float(maxs[0]),
        float(maxs[1]),
        float(maxs[2]),
    ]


def _preview_points_from_xyz(xyz: np.ndarray, *, limit: int = 500) -> list[list[float]]:
    if xyz.size <= 0 or limit <= 0:
        return []
    arr = np.asarray(xyz, dtype=np.float32).reshape((-1, 3))
    finite = np.isfinite(arr).all(axis=1)
    if not bool(finite.any()):
        return []
    arr = arr[finite]
    stride = max(1, int(np.ceil(arr.shape[0] / limit)))
    preview = np.round(arr[::stride][:limit], 3)
    return preview.astype(float, copy=False).tolist()


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


@dataclass
class _LayerRuntime:
    config: LiveMapSourceConfig
    sequence: int = 0
    last_publish_monotonic: float = 0.0
    queued_msg: Any | None = None
    processing: bool = False
    last_content_digest: str | None = None
    dropped_frames: int = 0
    last_backpressure_log_monotonic: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)


@dataclass
class _NvbloxLayersBridgeRuntime:
    node: Any
    executor: Any
    thread: threading.Thread
    sources: dict[str, _LayerRuntime]


_runtime: _NvbloxLayersBridgeRuntime | None = None
_runtime_lock = asyncio.Lock()


async def _store_and_publish_point_chunk(
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
    if has_rgb and rgb is not None:
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
    priority = render_priority_for_source(source.source_id)
    await asyncio.to_thread(
        warehouse_live_map_chunk_storage.save_chunk_metadata,
        flight_id=flight_id,
        chunk_id=stored.chunk_id,
        checksum_sha256=stored.checksum_sha256,
        metadata={
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
            "source_topic": source.topic,
        },
    )

    preview_points = _preview_points_from_xyz(xyz, limit=500)
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
                "missing_mesh": False,
                "mapping_recording": True,
                "stack_running": True,
            },
        }
    )
    await warehouse_live_map_stream.publish(update)
    logger.info(
        "Published nvblox layer live-map chunk flight_id=%s source=%s chunk_id=%s points=%s",
        flight_id,
        source.source_id,
        stored.chunk_id,
        int(xyz.shape[0]),
    )


async def _store_and_publish_mesh_chunk(
    *,
    flight_id: str,
    source: LiveMapSourceConfig,
    sequence: int,
    glb_bytes: bytes,
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

    chunk_id = chunk_id_for_source(source, sequence)
    stored = await warehouse_live_map_chunk_storage.save_upload(
        flight_id=flight_id,
        chunk_id=chunk_id,
        kind="mesh",
        upload=_MemoryUpload(glb_bytes, content_type="model/gltf-binary"),
        max_bytes=64 * 1024 * 1024,
    )
    priority = render_priority_for_source(source.source_id)
    await asyncio.to_thread(
        warehouse_live_map_chunk_storage.save_chunk_metadata,
        flight_id=flight_id,
        chunk_id=stored.chunk_id,
        checksum_sha256=stored.checksum_sha256,
        metadata={
            "source": source.source_id,
            "layer": source.layer,
            "layer_type": source.layer,
            "kind": "mesh",
            "sequence": sequence,
            "frame_id": frame_id,
            "content_type": "model/gltf-binary",
            "priority": priority,
            "stamp": stamp,
        },
    )
    update = normalize_live_map_payload(
        {
            "flight_id": flight_id,
            "frame_id": frame_id,
            "changed_chunks": [
                {
                    "id": stored.chunk_id,
                    "kind": "mesh",
                    "url": stored.url,
                    "content_type": stored.content_type,
                    "sequence": sequence,
                    "byte_size": stored.byte_size,
                    "checksum_sha256": stored.checksum_sha256,
                    "source": source.source_id,
                    "layer": source.layer,
                    "layer_type": source.layer,
                    "frame_id": frame_id,
                    "stamp": stamp,
                    "priority": priority,
                }
            ],
            "health": {
                "missing_point_cloud": False,
                "missing_mesh": False,
                "mapping_recording": True,
                "stack_running": True,
            },
        }
    )
    await warehouse_live_map_stream.publish(update)
    logger.info(
        "Published nvblox mesh live-map chunk flight_id=%s chunk_id=%s bytes=%s",
        flight_id,
        stored.chunk_id,
        stored.byte_size,
    )


class _NvbloxLayersLiveMapNode:
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

        class NodeImpl(Node):
            pass

        self.node = NodeImpl("warehouse_nvblox_layers_live_map_bridge")
        self.flight_id = flight_id
        self.event_loop = event_loop
        self.source_runtimes = {
            source_id: _LayerRuntime(config=config) for source_id, config in sources.items()
        }

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self.node)

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=3,
        )

        for source_id, config in sources.items():
            if source_id == "nvblox_mesh":
                from nvblox_msgs.msg import Mesh

                self.node.create_subscription(
                    Mesh,
                    config.topic,
                    self._make_mesh_callback(source_id),
                    sensor_qos,
                )
            elif config.kind == "occupancy":
                from nav_msgs.msg import OccupancyGrid

                self.node.create_subscription(
                    OccupancyGrid,
                    config.topic,
                    self._make_occupancy_callback(source_id),
                    sensor_qos,
                )
            else:
                from nvblox_msgs.msg import VoxelBlockLayer

                self.node.create_subscription(
                    VoxelBlockLayer,
                    config.topic,
                    self._make_voxel_callback(source_id),
                    sensor_qos,
                )
            self.node.get_logger().info(
                f"Nvblox layers bridge subscribed source={source_id} "
                f"topic={config.topic} flight_id={flight_id}"
            )

    def _make_voxel_callback(self, source_id: str):
        def _callback(msg: Any) -> None:
            self._on_message(source_id, msg)

        return _callback

    def _make_mesh_callback(self, source_id: str):
        def _callback(msg: Any) -> None:
            self._on_message(source_id, msg)

        return _callback

    def _make_occupancy_callback(self, source_id: str):
        def _callback(msg: Any) -> None:
            self._on_message(source_id, msg)

        return _callback

    def _lookup_transform(self, msg: Any, global_frame: str) -> Any | None:
        import rclpy
        from rclpy.duration import Duration
        from rclpy.time import Time

        header = getattr(msg, "header", None)
        source_frame = (getattr(header, "frame_id", None) or "").strip()
        if not source_frame or source_frame == global_frame:
            return None
        try:
            return self.tf_buffer.lookup_transform(
                global_frame,
                source_frame,
                Time.from_msg(header.stamp),
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
            except Exception:
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

    def _on_message(self, source_id: str, msg: Any) -> None:
        runtime = self.source_runtimes.get(source_id)
        if runtime is None:
            return
        config = runtime.config
        now = time.monotonic()
        if now - runtime.last_publish_monotonic < config.min_publish_interval_s:
            return
        start_worker = False
        with runtime.lock:
            runtime.last_publish_monotonic = now
            if runtime.processing:
                if runtime.queued_msg is not None:
                    runtime.dropped_frames += 1
                    if now - runtime.last_backpressure_log_monotonic >= 5.0:
                        runtime.last_backpressure_log_monotonic = now
                        self.node.get_logger().warning(
                            f"Nvblox layers bridge falling behind source={source_id}; "
                            f"dropped_stale_frames={runtime.dropped_frames}"
                        )
                runtime.queued_msg = msg
                return
            runtime.processing = True
            runtime.queued_msg = msg
            start_worker = True
        if not start_worker:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._drain_source(source_id),
            self.event_loop,
        )
        future.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)

    async def _drain_source(self, source_id: str) -> None:
        runtime = self.source_runtimes.get(source_id)
        if runtime is None:
            return
        try:
            while True:
                with runtime.lock:
                    msg = runtime.queued_msg
                    runtime.queued_msg = None
                if msg is None:
                    return
                await self._publish_source_message(source_id, msg)
        except Exception:
            self.node.get_logger().exception(
                "Failed to publish nvblox layer chunk source=%s",
                source_id,
            )
        finally:
            restart = False
            with runtime.lock:
                runtime.processing = False
                if runtime.queued_msg is not None:
                    runtime.processing = True
                    restart = True
            if restart:
                future = asyncio.run_coroutine_threadsafe(
                    self._drain_source(source_id),
                    self.event_loop,
                )
                future.add_done_callback(
                    lambda done: done.exception() if not done.cancelled() else None
                )

    async def _publish_source_message(self, source_id: str, msg: Any) -> None:
        runtime = self.source_runtimes.get(source_id)
        if runtime is None:
            return
        config = runtime.config
        nvblox_status_tracker.note_message(config.topic)

        if source_id == "nvblox_mesh":
            glb_bytes = await asyncio.to_thread(parse_nvblox_mesh_message, msg)
            if not glb_bytes:
                return
            digest = hashlib.sha1(glb_bytes).hexdigest()
            with runtime.lock:
                if runtime.last_content_digest == digest:
                    return
                runtime.last_content_digest = digest
                runtime.sequence += 1
                sequence = runtime.sequence
            await _store_and_publish_mesh_chunk(
                flight_id=self.flight_id,
                source=config,
                sequence=sequence,
                glb_bytes=glb_bytes,
                frame_id=config.global_frame,
                stamp=_stamp_from_msg(msg),
            )
            return

        if config.kind == "occupancy":
            parsed_grid = await asyncio.to_thread(parse_occupancy_grid_msg, msg)
            if parsed_grid is None:
                return
            payload = await asyncio.to_thread(encode_occupancy_grid, parsed_grid)
            digest = hashlib.sha1(payload).hexdigest()
            with runtime.lock:
                if runtime.last_content_digest == digest:
                    return
                runtime.last_content_digest = digest
                runtime.sequence += 1
                sequence = runtime.sequence
            await store_and_publish_occupancy_chunk(
                flight_id=self.flight_id,
                source=config,
                sequence=sequence,
                payload=payload,
                width=parsed_grid.width,
                height=parsed_grid.height,
                resolution_m=parsed_grid.resolution_m,
                origin_x_m=parsed_grid.origin_x_m,
                origin_y_m=parsed_grid.origin_y_m,
                frame_id=parsed_grid.frame_id or config.global_frame,
                stamp=_stamp_from_msg(msg),
            )
            return

        parse_started = time.monotonic()
        parsed = await asyncio.to_thread(
            parse_voxel_block_layer_msg,
            msg,
            max_points=config.max_points,
            require_color=source_id == "nvblox_color",
        )
        parse_ms = (time.monotonic() - parse_started) * 1000.0
        if parsed is None or parsed.point_count <= 0:
            return

        xyz = parsed.xyz
        header = getattr(msg, "header", None)
        source_frame = (getattr(header, "frame_id", None) or "").strip()
        transform = self._lookup_transform(msg, config.global_frame)
        if source_frame and source_frame != config.global_frame and transform is None:
            self.node.get_logger().warning(
                "Skipping nvblox layer chunk source=%s: TF %s <- %s unavailable",
                source_id,
                config.global_frame,
                source_frame,
            )
            return
        xyz = self._transform_xyz(xyz, transform)

        digest = hashlib.sha1()
        digest.update(config.source_id.encode("utf-8"))
        digest.update(np.ascontiguousarray(xyz).view(np.uint8))
        if parsed.rgb is not None:
            digest.update(np.ascontiguousarray(parsed.rgb).view(np.uint8))
        content_digest = digest.hexdigest()
        with runtime.lock:
            if runtime.last_content_digest == content_digest:
                return
            runtime.last_content_digest = content_digest
            runtime.sequence += 1
            sequence = runtime.sequence
        publish_started = time.monotonic()
        await _store_and_publish_point_chunk(
            flight_id=self.flight_id,
            source=config,
            sequence=sequence,
            xyz=xyz,
            rgb=parsed.rgb,
            has_rgb=parsed.has_rgb,
            frame_id=config.global_frame,
            stamp=_stamp_from_msg(msg),
        )
        total_ms = (time.monotonic() - parse_started) * 1000.0
        publish_ms = (time.monotonic() - publish_started) * 1000.0
        logger.info(
            "nvblox_layer_bridge_timing source=%s points=%s parse_ms=%.1f "
            "publish_ms=%.1f total_ms=%.1f dropped=%s",
            source_id,
            parsed.point_count,
            parse_ms,
            publish_ms,
            total_ms,
            runtime.dropped_frames,
        )


def resolve_nvblox_layer_bridge_sources(
    *,
    topics: set[str] | None = None,
) -> dict[str, LiveMapSourceConfig]:
    from backend.infrastructure.warehouse.bridge_config import list_ros2_topics
    from backend.modules.warehouse.service.live_map_readiness import (
        _ros2_workspace,
        probe_live_map_topic_types,
    )

    if topics is None:
        ws = _ros2_workspace()
        try:
            topics = set(list_ros2_topics(ws))
        except RuntimeError:
            topics = set()

    _, topic_types = probe_live_map_topic_types(topics=topics, quiet=True)
    sources: dict[str, LiveMapSourceConfig] = {}

    # color_layer and tsdf_layer publish nvBlox voxel blocks. Their presence is
    # reported by readiness diagnostics, but they are not user-facing map products.

    mesh_topic = WAREHOUSE_LIVE_MAP_SOURCES["nvblox_mesh"].topic
    mesh_type = topic_types.get(mesh_topic)
    if mesh_topic in topics and mesh_type and "nvblox_msgs/msg/Mesh" in mesh_type:
        sources["nvblox_mesh"] = WAREHOUSE_LIVE_MAP_SOURCES["nvblox_mesh"]

    occupancy_candidates = (
        *OCCUPANCY_TOPIC_CANDIDATES,
        "/nvblox_node/static_map_slice",
        "/nvblox_node/occupancy_grid",
        "/nvblox_node/map_slice",
    )
    for occupancy_topic in occupancy_candidates:
        occupancy_type = topic_types.get(occupancy_topic)
        if (
            occupancy_topic in topics
            and occupancy_type
            and "nav_msgs/msg/OccupancyGrid" in occupancy_type
        ):
            sources["nvblox_occupancy"] = replace(
                WAREHOUSE_LIVE_MAP_SOURCES["nvblox_occupancy"],
                topic=occupancy_topic,
            )
            break

    return sources


async def start_nvblox_layers_live_map_bridge(flight_id: str) -> None:
    global _runtime

    async with _runtime_lock:
        await stop_nvblox_layers_live_map_bridge()

        sources = resolve_nvblox_layer_bridge_sources()
        if not sources:
            logger.info(
                "Skipping nvblox layers live-map bridge for flight_id=%s (no layer topics)",
                flight_id,
            )
            return

        import rclpy
        from rclpy.executors import SingleThreadedExecutor

        if not rclpy.ok():
            rclpy.init(args=None)

        loop = asyncio.get_running_loop()
        wrapper = _NvbloxLayersLiveMapNode(
            flight_id=flight_id,
            event_loop=loop,
            sources=sources,
        )
        executor = SingleThreadedExecutor()
        executor.add_node(wrapper.node)
        thread = threading.Thread(
            target=executor.spin,
            name="warehouse-nvblox-layers-live-map-bridge",
            daemon=True,
        )
        thread.start()
        _runtime = _NvbloxLayersBridgeRuntime(
            node=wrapper.node,
            executor=executor,
            thread=thread,
            sources=wrapper.source_runtimes,
        )
        logger.info(
            "Started nvblox layers live-map bridge flight_id=%s sources=%s",
            flight_id,
            list(sources.keys()),
        )


async def stop_nvblox_layers_live_map_bridge() -> None:
    global _runtime

    runtime = _runtime
    _runtime = None
    if runtime is None:
        return
    try:
        await asyncio.to_thread(runtime.executor.shutdown)
    except Exception:
        logger.exception("Failed to shutdown nvblox layers executor")
    try:
        runtime.node.destroy_node()
    except Exception:
        logger.exception("Failed to destroy nvblox layers node")
    if runtime.thread.is_alive():
        await asyncio.to_thread(runtime.thread.join, 2.0)
    logger.info("Stopped nvblox layers live-map bridge")
