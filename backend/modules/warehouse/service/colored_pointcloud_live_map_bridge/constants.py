"""Colored point-cloud live-map bridge — constants."""

from __future__ import annotations

COLORED_BRIDGE_SOURCES: tuple[str, ...] = (
    "rgbd_colored",
    "nvblox_esdf",
)
_MAX_PREVIEW_POINTS = 500
_MAX_CHUNK_BYTES = 48 * 1024 * 1024

__all__ = ["COLORED_BRIDGE_SOURCES", "_MAX_CHUNK_BYTES", "_MAX_PREVIEW_POINTS"]
