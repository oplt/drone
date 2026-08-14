"""Colored point-cloud live-map bridge — chunk encoding helpers."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
from typing import Any

import numpy as np

from backend.modules.warehouse.service.live_map_config import render_priority_for_source
from backend.modules.warehouse.service.map_source_config import LiveMapSourceConfig
from backend.modules.warehouse.service.pointcloud2_parser import encode_xyz32, encode_xyzrgb32
from backend.modules.warehouse.service.startup_timing_hooks import note_mapping_startup_safe
from backend.observability.instruments import observed_span, structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

from .constants import _MAX_CHUNK_BYTES, _MAX_PREVIEW_POINTS

logger = logging.getLogger(__name__)


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

    from backend.modules.warehouse.service.map_source_config import chunk_id_for_source

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


__all__ = [
    "_content_digest",
    "_finite_xyz_rows",
    "_log_future_exception",
    "_note_mapping_startup",
    "_store_and_publish_colored_chunk",
]
