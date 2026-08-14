from __future__ import annotations

import asyncio

from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.cache.local import BoundedTTLCache

GZ_TO_ROS = "GZ_TO_ROS"
ROS_TO_GZ = "ROS_TO_GZ"
_BRIDGE_DIAGNOSTICS_CACHE = BoundedTTLCache[dict[str, Any]](max_entries=32)
_BRIDGE_DIAGNOSTICS_LOCK = asyncio.Lock()


def _raw_lidar_required() -> bool:
    return bool(
        getattr(settings, "warehouse_live_map_raw_lidar_enabled", False)
        or getattr(settings, "warehouse_include_raw_lidar_preview", False)
        or getattr(settings, "warehouse_persist_raw_lidar_layer", False)
    )
