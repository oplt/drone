"""Live-map flight manifest — constants."""

from __future__ import annotations

import re

_MANIFEST_NAME = "live_map_manifest.json"
_CHUNK_ID_RE = re.compile(
    r"^(rgbd|rgbd_colored|rgbd_xyz|mid360|mid360_raw|nvblox_color|nvblox_esdf|"
    r"nvblox_tsdf|nvblox_mesh|nvblox_occupancy)_",
    re.IGNORECASE,
)

__all__ = ["_CHUNK_ID_RE", "_MANIFEST_NAME"]
