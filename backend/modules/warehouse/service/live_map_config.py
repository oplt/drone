from __future__ import annotations

from typing import Any

from backend.core.config.runtime import env_truthy, settings
from backend.modules.warehouse.service.map_source_config import LiveMapSourceId

SOURCE_RENDER_PRIORITY: dict[LiveMapSourceId, int] = {
    "rgbd_colored": 1,
    "rgbd_xyz_uncolored": 2,
    "nvblox_esdf": 3,
    "nvblox_mesh": 4,
    "mid360_raw": 5,
    "nvblox_occupancy": 6,
    # Voxel block layers are diagnostic transport topics, not scanned-map products.
    "nvblox_color": 90,
    "nvblox_tsdf": 91,
    "odom": 99,
}

PREFERRED_LAYER_CHOICES = frozenset(
    {"rgbd_colored", "rgbd_xyz_uncolored", "nvblox_esdf", "nvblox_mesh", "mid360_raw"}
)


def _setting_bool(name: str, default: bool = False) -> bool:
    raw = getattr(settings, name, default)
    if isinstance(raw, str):
        return env_truthy(raw)
    return bool(raw)


def _setting_float(name: str, default: float, *, minimum: float) -> float:
    try:
        return max(minimum, float(getattr(settings, name, default)))
    except (TypeError, ValueError):
        return max(minimum, default)


def _setting_int(name: str, default: int, *, minimum: int) -> int:
    try:
        return max(minimum, int(getattr(settings, name, default)))
    except (TypeError, ValueError):
        return max(minimum, default)


def raw_lidar_enabled() -> bool:
    return _setting_bool("warehouse_live_map_raw_lidar_enabled", False) or _setting_bool(
        "warehouse_include_raw_lidar_preview",
        False,
    )


def include_raw_lidar_preview() -> bool:
    return raw_lidar_enabled()


def persist_raw_lidar_layer() -> bool:
    return _setting_bool("warehouse_persist_raw_lidar_layer", False)


def should_persist_raw_lidar_chunks() -> bool:
    """Persist Mid360 chunks when live streaming is on or persistence is forced."""
    return raw_lidar_enabled() or persist_raw_lidar_layer()


def raw_lidar_max_hz() -> float:
    return _setting_float("warehouse_live_map_raw_lidar_max_hz", 0.5, minimum=0.1)


def raw_lidar_voxel_size_m() -> float:
    return _setting_float("warehouse_live_map_raw_lidar_voxel_size", 0.15, minimum=0.01)


def raw_lidar_min_publish_interval_s() -> float:
    return 1.0 / raw_lidar_max_hz()


def raw_lidar_max_points() -> int:
    return _setting_int("warehouse_live_map_raw_lidar_max_points", 8000, minimum=1000)


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
    return _setting_bool("warehouse_require_rgb_for_save", True)


def frontend_max_concurrent_chunk_downloads() -> int:
    return _setting_int(
        "warehouse_live_map_frontend_max_concurrent_chunk_downloads",
        4,
        minimum=1,
    )


def frontend_max_points_per_layer() -> int:
    return _setting_int(
        "warehouse_live_map_frontend_max_points_per_layer",
        800_000,
        minimum=10_000,
    )


def render_priority_for_source(source_id: str) -> int:
    return SOURCE_RENDER_PRIORITY.get(source_id, 50)  # type: ignore[arg-type]


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
