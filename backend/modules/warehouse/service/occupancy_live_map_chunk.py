from __future__ import annotations

import asyncio
import io
import logging

from backend.modules.warehouse.service.live_map_config import render_priority_for_source
from backend.modules.warehouse.service.map_source_config import (
    LiveMapSourceConfig,
    chunk_id_for_source,
)
from backend.modules.warehouse.service.occupancy_grid_parser import (
    OccupancyGridOrigin,
    OCCUPANCY_ENCODING_V2,
    occupancy_grid_bbox_local_m,
)

logger = logging.getLogger(__name__)


class MemoryUpload:
    content_type = "application/octet-stream"

    def __init__(self, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._buffer = io.BytesIO(data)
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


async def store_and_publish_occupancy_chunk(
    *,
    flight_id: str,
    source: LiveMapSourceConfig,
    sequence: int,
    payload: bytes,
    width: int,
    height: int,
    resolution_m: float,
    origin: OccupancyGridOrigin,
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
        frame_id=frame_id,
        kind="occupancy",
        upload=MemoryUpload(payload, content_type="application/vnd.live-map.occupancy-grid+json"),
        max_bytes=64 * 1024 * 1024,
    )
    priority = render_priority_for_source(source.source_id)
    bbox = occupancy_grid_bbox_local_m(
        width=width,
        height=height,
        resolution_m=resolution_m,
        origin=origin,
    )
    origin_dict = origin.as_dict()
    await asyncio.to_thread(
        warehouse_live_map_chunk_storage.save_chunk_metadata,
        flight_id=flight_id,
        chunk_id=stored.chunk_id,
        checksum_sha256=stored.checksum_sha256,
        metadata={
            "source": source.source_id,
            "layer": source.layer,
            "layer_type": source.layer,
            "kind": "occupancy",
            "encoding": OCCUPANCY_ENCODING_V2,
            "sequence": sequence,
            "width": int(width),
            "height": int(height),
            "resolution_m": float(resolution_m),
            "origin": origin_dict,
            "origin_x_m": float(origin.x_m),
            "origin_y_m": float(origin.y_m),
            "origin_z_m": float(origin.z_m),
            "bbox_local_m": bbox,
            "frame_id": frame_id,
            "content_type": "application/vnd.live-map.occupancy-grid+json",
            "priority": priority,
            "stamp": stamp,
            "source_topic": source.topic,
        },
    )
    update = normalize_live_map_payload(
        {
            "flight_id": flight_id,
            "frame_id": frame_id,
            "changed_chunks": [
                {
                    "id": stored.chunk_id,
                    "kind": "occupancy",
                    "url": stored.url,
                    "content_type": stored.content_type,
                    "sequence": sequence,
                    "byte_size": stored.byte_size,
                    "checksum_sha256": stored.checksum_sha256,
                    "bbox_local_m": bbox,
                    "source": source.source_id,
                    "layer": source.layer,
                    "layer_type": source.layer,
                    "encoding": OCCUPANCY_ENCODING_V2,
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
        "Published nvblox occupancy live-map chunk flight_id=%s chunk_id=%s cells=%s",
        flight_id,
        stored.chunk_id,
        int(width) * int(height),
    )
