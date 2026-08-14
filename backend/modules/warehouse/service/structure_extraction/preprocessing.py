"""Warehouse structure extraction — preprocessing."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.modules.warehouse.planning.indoor.models import OccupancyGrid
from backend.modules.warehouse.service.occupancy_grid_parser import decode_occupancy_grid

from .constants import _EXCLUDED_SOURCE_PREFIXES, _POINT_SUFFIXES
from .deps import resolve_chunk_storage
from .models import StructureExtractionError, StructureExtractionParams

def _decode_chunk_file(path: Path) -> np.ndarray | None:
    """Decode an on-disk live-map chunk into an (N, 3) float32 XYZ array."""
    suffix = path.suffix.lower()
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data:
        return None
    if suffix == ".xyz32":
        arr = np.frombuffer(data, dtype=np.float32)
        n = arr.size // 3
        if n == 0:
            return None
        return np.ascontiguousarray(arr[: n * 3].reshape(n, 3))
    if suffix == ".xyzrgb32":
        # encode_xyzrgb32: float32 positions (12 bytes/pt) + uint8 rgb (3 bytes/pt)
        n = len(data) // 15
        if n == 0:
            return None
        xyz = np.frombuffer(data[: n * 12], dtype=np.float32).reshape(n, 3)
        return np.ascontiguousarray(xyz)
    return None

def _is_surface_chunk(chunk_id: str) -> bool:
    lower = chunk_id.lower()
    return not lower.startswith(_EXCLUDED_SOURCE_PREFIXES)

def load_flight_occupancy_grid(client_flight_id: str) -> OccupancyGrid | None:
    """Load the latest persisted nvblox occupancy grid for collision-aware routing."""
    candidates = [
        chunk
        for chunk in resolve_chunk_storage().iter_chunk_files(flight_id=client_flight_id)
        if chunk.path.suffix.lower() in {".grid", ".vox"}
        and chunk.chunk_id.lower().startswith("nvblox_occupancy_")
    ]
    for chunk in sorted(candidates, key=lambda item: item.path.stat().st_mtime, reverse=True):
        try:
            grid = decode_occupancy_grid(chunk.path.read_bytes())
        except OSError:
            continue
        if grid is not None:
            return grid
    return None

def load_flight_cloud(
    client_flight_id: str,
    *,
    params: StructureExtractionParams,
) -> np.ndarray:
    """Merge + voxel-downsample all surface chunks for a flight.

    Returns an (N, 3) float32 array in the warehouse_map frame. Raises
    ``StructureExtractionError`` when no usable points are found.
    """
    stored = resolve_chunk_storage().iter_chunk_files(flight_id=client_flight_id)
    clouds: list[np.ndarray] = []
    total = 0
    for chunk in stored:
        if chunk.path.suffix.lower() not in _POINT_SUFFIXES:
            continue
        if not _is_surface_chunk(chunk.chunk_id):
            continue
        arr = _decode_chunk_file(chunk.path)
        if arr is None or arr.shape[0] == 0:
            continue
        clouds.append(arr)
        total += arr.shape[0]
        if total >= params.max_points:
            break

    if not clouds:
        raise StructureExtractionError(
            f"No surface point-cloud chunks found for flight {client_flight_id!r}."
        )

    merged = np.concatenate(clouds, axis=0)
    # Drop non-finite rows before any quantization.
    finite = np.isfinite(merged).all(axis=1)
    merged = merged[finite]
    if merged.shape[0] == 0:
        raise StructureExtractionError("All merged points were non-finite.")

    downsampled = voxel_downsample(merged, params.voxel_m)
    if params.min_surface_points and downsampled.shape[0] < params.min_surface_points:
        raise StructureExtractionError(
            "Insufficient map coverage: "
            f"{downsampled.shape[0]} surface points after voxel downsample, "
            f"minimum={params.min_surface_points}."
        )
    return downsampled

def voxel_downsample(xyz: np.ndarray, voxel_m: float) -> np.ndarray:
    """Keep one representative point per occupied voxel (first-seen)."""
    if xyz.shape[0] == 0 or voxel_m <= 0:
        return xyz
    keys = np.floor(xyz / float(voxel_m)).astype(np.int64)
    keys -= keys.min(axis=0)
    dims = keys.max(axis=0) + 1
    # Linearize voxel coords into a single int64 key; guard against overflow by
    # falling back to np.unique on the raw rows for pathological extents.
    span = int(dims[0]) * int(dims[1]) * int(dims[2])
    if span <= 0 or span > (1 << 62):
        _, idx = np.unique(keys, axis=0, return_index=True)
    else:
        lin = (keys[:, 0] * int(dims[1]) + keys[:, 1]) * int(dims[2]) + keys[:, 2]
        _, idx = np.unique(lin, return_index=True)
    return np.ascontiguousarray(xyz[np.sort(idx)])
