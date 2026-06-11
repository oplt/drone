from __future__ import annotations

from typing import Any

from backend.core.config.runtime import settings
from backend.modules.warehouse.service.map_source_config import LiveMapSourceId

SOURCE_RENDER_PRIORITY: dict[LiveMapSourceId, int] = {
    "nvblox_color": 1,
    "rgbd_colored": 2,
    "nvblox_esdf": 3,
    "nvblox_tsdf": 4,
    "mid360_raw": 5,
    "nvblox_mesh": 6,
    "odom": 99,
}

PREFERRED_LAYER_CHOICES = frozenset({"rgbd_colored", "nvblox_color", "mid360_raw"})


def raw_lidar_enabled() -> bool:
    if bool(getattr(settings, "warehouse_live_map_raw_lidar_enabled", False)):
        return True
    return bool(getattr(settings, "warehouse_include_raw_lidar_preview", False))


def include_raw_lidar_preview() -> bool:
    return raw_lidar_enabled()


def persist_raw_lidar_layer() -> bool:
    return bool(getattr(settings, "warehouse_persist_raw_lidar_layer", False))


def raw_lidar_max_hz() -> float:
    return max(0.1, float(getattr(settings, "warehouse_live_map_raw_lidar_max_hz", 0.5)))


def raw_lidar_voxel_size_m() -> float:
    return max(0.01, float(getattr(settings, "warehouse_live_map_raw_lidar_voxel_size", 0.15)))


def raw_lidar_min_publish_interval_s() -> float:
    return 1.0 / raw_lidar_max_hz()


def raw_lidar_max_points() -> int:
    return max(1000, int(getattr(settings, "warehouse_live_map_raw_lidar_max_points", 8000)))


def preferred_map_layer() -> str:
    value = str(
        getattr(settings, "warehouse_live_map_preferred_layer", None)
        or getattr(settings, "warehouse_preferred_map_layer", "")
        or "",
    ).strip()
    if value in PREFERRED_LAYER_CHOICES:
        return value
    return "rgbd_colored"


def require_rgb_for_save() -> bool:
    return bool(getattr(settings, "warehouse_require_rgb_for_save", True))


def frontend_max_concurrent_chunk_downloads() -> int:
    return max(
        1,
        int(getattr(settings, "warehouse_live_map_frontend_max_concurrent_chunk_downloads", 4)),
    )


def frontend_max_points_per_layer() -> int:
    return max(
        10_000,
        int(getattr(settings, "warehouse_live_map_frontend_max_points_per_layer", 800_000)),
    )


def render_priority_for_source(source_id: str) -> int:
    try:
        return SOURCE_RENDER_PRIORITY[source_id]  # type: ignore[index]
    except KeyError:
        return 50


def live_map_public_config() -> dict[str, Any]:
    return {
        "live_map": {
            "raw_lidar": {
                "enabled": raw_lidar_enabled(),
                "max_hz": raw_lidar_max_hz(),
                "voxel_size": raw_lidar_voxel_size_m(),
                "max_points": raw_lidar_max_points(),
            },
            "frontend": {
                "max_concurrent_chunk_downloads": frontend_max_concurrent_chunk_downloads(),
                "max_points_per_layer": frontend_max_points_per_layer(),
            },
            "preferred_layer": preferred_map_layer(),
        }
    }
