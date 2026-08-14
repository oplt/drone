"""Live-map flight manifest — chunk id and source inference."""

from __future__ import annotations

from pathlib import Path

from .constants import _CHUNK_ID_RE


def _infer_source_from_chunk_id(chunk_id: str) -> str:
    lower = chunk_id.lower()
    if lower.startswith("rgbd_xyz_"):
        return "rgbd_xyz_uncolored"
    if lower.startswith(("rgbd_colored_", "rgbd_")):
        return "rgbd_colored"
    if lower.startswith(("mid360_raw_", "mid360_")):
        return "mid360_raw"
    if lower.startswith("nvblox_color_"):
        return "nvblox_color"
    if lower.startswith("nvblox_esdf_"):
        return "nvblox_esdf"
    if lower.startswith("nvblox_tsdf_"):
        return "nvblox_tsdf"
    if lower.startswith("nvblox_mesh_"):
        return "nvblox_mesh"
    if lower.startswith("nvblox_occupancy_"):
        return "nvblox_occupancy"
    return "unknown"


def _chunk_id_from_path(path: Path) -> str | None:
    name = path.name.lower()
    if name.endswith(".meta.json") or name.endswith(".uploading") or name.endswith(".preview.json"):
        return None
    chunk_id = path.stem.rsplit("-", 1)[0]
    if not _CHUNK_ID_RE.match(chunk_id):
        return None
    return chunk_id


__all__ = ["_chunk_id_from_path", "_infer_source_from_chunk_id"]
