"""Live-map flight manifest — test monkeypatching helpers."""

from __future__ import annotations

from backend.modules.warehouse.service.live_map_config import (
    require_rgb_for_save as _default_require_rgb_for_save,
)
from backend.modules.warehouse.service.live_map_storage import (
    warehouse_live_map_chunk_storage as _default_warehouse_live_map_chunk_storage,
)

require_rgb_for_save = _default_require_rgb_for_save
warehouse_live_map_chunk_storage = _default_warehouse_live_map_chunk_storage


def resolve(name: str):
    from backend.modules.warehouse.service import live_map_manifest as pkg

    return getattr(pkg, name)


def resolve_chunk_storage():
    from backend.modules.warehouse.service import live_map_manifest as pkg

    return pkg.warehouse_live_map_chunk_storage


__all__ = [
    "require_rgb_for_save",
    "resolve",
    "resolve_chunk_storage",
    "warehouse_live_map_chunk_storage",
]
