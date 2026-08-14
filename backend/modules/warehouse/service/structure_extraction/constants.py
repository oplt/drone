"""Warehouse structure extraction — shared constants."""

from __future__ import annotations

_SURFACE_SOURCE_PREFIXES = (
    "nvblox_tsdf_",
    "nvblox_color_",
    "rgbd_colored_",
    "rgbd_",
    "mid360_raw_",
    "mid360_",
)

_EXCLUDED_SOURCE_PREFIXES = (
    "nvblox_esdf_",
    "nvblox_mesh_",
)

_POINT_SUFFIXES = (".xyz32", ".xyzrgb32")
