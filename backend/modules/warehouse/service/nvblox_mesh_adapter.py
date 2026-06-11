"""
Optional nvBlox mesh adapter.

TODO(mesh): Implement parsing for `/nvblox_node/mesh` (nvblox_msgs/msg/Mesh) and
`/nvblox_node/mesh_marker` (visualization_msgs/msg/Marker) once the exact message
layout is confirmed in the deployed ROS stack.

Requirements when implemented:
- Convert triangle mesh to GLB bytes for live_map_storage kind="mesh"
- Publish chunks with id prefix `nvblox_mesh_######`
- Wire through colored_pointcloud_live_map_bridge or a dedicated mesh subscriber
"""

from __future__ import annotations

from typing import Any


def mesh_topic_supported() -> bool:
    return False


def parse_nvblox_mesh_message(_msg: Any) -> bytes | None:
    return None
