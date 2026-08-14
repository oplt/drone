"""Raw point-cloud live-map bridge — defaults."""

from __future__ import annotations

from backend.modules.warehouse.service.map_source_config import WAREHOUSE_LIVE_MAP_SOURCES

DEFAULT_POINTCLOUD_TOPIC = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].topic
DEFAULT_GLOBAL_FRAME = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].global_frame
DEFAULT_MAX_POINTS = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].max_points
DEFAULT_MIN_PUBLISH_INTERVAL_S = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].min_publish_interval_s
_MAX_CHUNK_BYTES = 32 * 1024 * 1024
_MAX_PREVIEW_POINTS = 500

__all__ = [
    "DEFAULT_GLOBAL_FRAME",
    "DEFAULT_MAX_POINTS",
    "DEFAULT_MIN_PUBLISH_INTERVAL_S",
    "DEFAULT_POINTCLOUD_TOPIC",
    "_MAX_CHUNK_BYTES",
    "_MAX_PREVIEW_POINTS",
]
