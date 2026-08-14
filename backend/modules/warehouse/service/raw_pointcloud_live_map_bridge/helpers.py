"""Raw point-cloud live-map bridge — point cloud helpers and publish."""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Any

import numpy as np

from backend.modules.warehouse.service.live_map_config import render_priority_for_source
from backend.modules.warehouse.service.map_source_config import (
    WAREHOUSE_LIVE_MAP_SOURCES,
    chunk_id_for_source,
)
from backend.observability.instruments import observed_span, structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

from .constants import _MAX_CHUNK_BYTES, _MAX_PREVIEW_POINTS

logger = logging.getLogger(__name__)


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


def _preview_points(xyz: np.ndarray, *, limit: int = _MAX_PREVIEW_POINTS) -> list[list[float]]:
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


async def _store_and_publish_pointcloud_chunk(
    *,
    flight_id: str,
    sequence: int,
    xyz: np.ndarray,
    persist_to_disk: bool,
    stamp: str | None = None,
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
                    frame_id=mid360_source.global_frame,
                    kind="point_cloud",
                    upload=_MemoryUpload(payload),
                    max_bytes=_MAX_CHUNK_BYTES,
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
                "cloud_age_ms": cloud_age_ms,
                "transform_age_ms": transform_age_ms,
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
        "cloud_age_ms": cloud_age_ms,
        "transform_age_ms": transform_age_ms,
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
            "frame_id": mid360_source.global_frame,
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


__all__ = [
    "_finite_xyz",
    "_safe_xyz_array",
    "_store_and_publish_pointcloud_chunk",
    "_voxel_downsample",
]
