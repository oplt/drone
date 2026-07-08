"""Automatic warehouse structure extraction.

Turns a finished warehouse 3D map (the live-map point-cloud chunks saved on disk
for a flight) into a hierarchy of aisles -> racks -> shelves -> bins, each with a
metric centre point and a shelf-face normal, and emits ready-to-fly
``WarehouseScanTarget`` rows.

Design goals
------------
* Pure ``numpy`` / ``scipy`` (no Open3D / sklearn dependency); deterministic.
* Synchronous + side-effect free: this module only computes. Persistence and
  enqueueing live in the Celery task / API layer so it stays re-runnable and unit
  testable.
* Source chunks are ``odom`` data. A locked localization transform is required
  and applied before extraction; outputs are stable ``warehouse_map`` data.

Pipeline (see prompt.txt sections 2 & 5):
    P0  load + merge + voxel-downsample flight chunks
    A   floor / ceiling removal -> vertical "rack mass"
    B   dominant aisle axis (PCA) -> cross-axis density profile -> rack rows + aisles
    C   along-axis segmentation of each rack row -> rack bays + face normals
    D   z-histogram -> shelf levels; bin pitch -> bins -> scan targets
    +   clearance gate (KD-tree distance to structure) on every scan pose
    +   aisle-aware serpentine ordering (priority) for collision-light routing
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid
from backend.modules.warehouse.schemas import (
    WAREHOUSE_MAP_FRAME_ID,
    WarehouseLocalPoint,
    WarehouseShelfNormal,
)
from backend.modules.warehouse.service.coordinate_frames import transform_odom_points
from backend.modules.warehouse.service.inspection import compute_scan_pose
from backend.modules.warehouse.service.live_map_storage import (
    warehouse_live_map_chunk_storage,
)
from backend.modules.warehouse.service.occupancy_grid_parser import decode_occupancy_grid

logger = logging.getLogger(__name__)

# Chunk id prefixes whose points describe real surfaces (good for geometry).
# ESDF (distance field) and occupancy/cost layers are excluded because their
# points do not lie on physical surfaces.
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


class StructureExtractionError(RuntimeError):
    pass


@dataclass(slots=True)
class StructureExtractionParams:
    """Tunables for the geometry heuristics + clearance gate."""

    voxel_m: float = 0.05
    grid_res_m: float = 0.10
    floor_margin_m: float = 0.15
    ceiling_max_m: float = 8.0
    min_aisle_width_m: float = 0.9
    min_rack_length_m: float = 0.6
    bin_pitch_m: float = 0.9
    shelf_min_spacing_m: float = 0.30
    max_shelf_levels: int = 6
    max_bins_per_rack_face: int = 24
    min_target_spacing_m: float = 0.75
    review_clearance_m: float = 0.10
    standoff_m: float = 1.2
    drone_radius_m: float = 0.35
    clearance_margin_m: float = 0.25
    max_points: int = 6_000_000
    min_surface_points: int = 0
    barcode_scan_expected: bool = False
    rack_template_version_id: int | None = None
    rack_template_bin_count: int | None = None
    rack_template_bay_width_m: float | None = None
    rack_template_shelf_levels_m: tuple[float, ...] = ()
    # Optional operator override for the aisle axis (degrees CCW from +X).
    axis_deg: float | None = None

    @property
    def required_clearance_m(self) -> float:
        return float(self.drone_radius_m) + float(self.clearance_margin_m)

    def sanitized(self) -> StructureExtractionParams:
        def _pos(value: float, default: float, *, minimum: float = 1e-4) -> float:
            try:
                v = float(value)
            except (TypeError, ValueError):
                return default
            if not math.isfinite(v) or v < minimum:
                return default
            return v

        return StructureExtractionParams(
            voxel_m=_pos(self.voxel_m, 0.05),
            grid_res_m=_pos(self.grid_res_m, 0.10),
            floor_margin_m=_pos(self.floor_margin_m, 0.15, minimum=0.0),
            ceiling_max_m=_pos(self.ceiling_max_m, 8.0),
            min_aisle_width_m=_pos(self.min_aisle_width_m, 0.9),
            min_rack_length_m=_pos(self.min_rack_length_m, 0.6),
            bin_pitch_m=_pos(self.bin_pitch_m, 0.9),
            shelf_min_spacing_m=_pos(self.shelf_min_spacing_m, 0.30),
            max_shelf_levels=max(1, min(12, int(self.max_shelf_levels or 6))),
            max_bins_per_rack_face=max(1, min(80, int(self.max_bins_per_rack_face or 24))),
            min_target_spacing_m=_pos(self.min_target_spacing_m, 0.75),
            review_clearance_m=_pos(self.review_clearance_m, 0.10, minimum=0.0),
            standoff_m=_pos(self.standoff_m, 1.2),
            drone_radius_m=_pos(self.drone_radius_m, 0.35),
            clearance_margin_m=_pos(self.clearance_margin_m, 0.25, minimum=0.0),
            max_points=max(10_000, int(self.max_points or 6_000_000)),
            min_surface_points=max(0, int(self.min_surface_points or 0)),
            barcode_scan_expected=bool(self.barcode_scan_expected),
            rack_template_version_id=(
                None
                if self.rack_template_version_id is None
                else max(1, int(self.rack_template_version_id))
            ),
            rack_template_bin_count=(
                None
                if self.rack_template_bin_count is None
                else max(1, min(80, int(self.rack_template_bin_count)))
            ),
            rack_template_bay_width_m=(
                None
                if self.rack_template_bay_width_m is None
                else _pos(self.rack_template_bay_width_m, 1.0)
            ),
            rack_template_shelf_levels_m=_clean_template_levels(
                self.rack_template_shelf_levels_m
            ),
            axis_deg=(None if self.axis_deg is None else float(self.axis_deg)),
        )


@dataclass(slots=True)
class GeneratedTarget:
    aisle_code: str
    rack_code: str
    shelf_level: int
    bin_code: str
    target_point: dict[str, Any]
    shelf_normal: dict[str, Any]
    scan_pose: dict[str, Any]
    standoff_m: float
    priority: int
    clearance_status: str = "needs_review"
    clearance_m: float | None = None
    clearance_source: str = "point_cloud_kdtree"
    confidence: float = 0.5
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    template_metadata: dict[str, Any] = field(default_factory=dict)
    scanner_metadata: dict[str, Any] = field(default_factory=dict)
    path_validation: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None


@dataclass(slots=True)
class StructureResult:
    targets: list[GeneratedTarget] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    point_count: int = 0
    rejected_clearance: int = 0
    rejection_diagnostics: list[dict[str, Any]] = field(default_factory=list)


def classify_clearance(
    clearance_m: float,
    *,
    strict_clearance_m: float,
    review_clearance_m: float,
    reliable_evidence: bool,
) -> str:
    if clearance_m >= strict_clearance_m:
        return "active" if reliable_evidence else "needs_review"
    if clearance_m >= review_clearance_m:
        return "needs_review"
    return "rejected"


# --------------------------------------------------------------------------- #
# P0 — chunk loading / merge / voxel downsample
# --------------------------------------------------------------------------- #
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
        for chunk in warehouse_live_map_chunk_storage.iter_chunk_files(flight_id=client_flight_id)
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
    stored = warehouse_live_map_chunk_storage.iter_chunk_files(flight_id=client_flight_id)
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


# --------------------------------------------------------------------------- #
# Stage A — floor / ceiling separation
# --------------------------------------------------------------------------- #
def _detect_floor_z(z: np.ndarray, grid_res_m: float) -> float:
    """Floor height = densest z-bin within the lowest part of the cloud."""
    z_min = float(np.percentile(z, 0.5))
    z_max = float(np.percentile(z, 99.5))
    if z_max - z_min < grid_res_m:
        return z_min
    bins = max(8, math.ceil((z_max - z_min) / grid_res_m))
    hist, edges = np.histogram(z, bins=bins, range=(z_min, z_max))
    # Restrict floor search to the bottom third of the height range.
    cutoff = z_min + (z_max - z_min) * 0.34
    mask = edges[:-1] <= cutoff
    if not mask.any():
        return z_min
    region = np.where(mask, hist, 0)
    peak = int(np.argmax(region))
    return float((edges[peak] + edges[peak + 1]) * 0.5)


# --------------------------------------------------------------------------- #
# Stage B — dominant aisle axis + cross-axis density profile
# --------------------------------------------------------------------------- #
def _dominant_axis_rad(xy: np.ndarray) -> float:
    """PCA major axis of the XY footprint (radians, CCW from +X)."""
    centered = xy - xy.mean(axis=0, keepdims=True)
    cov = np.cov(centered.T)
    if not np.all(np.isfinite(cov)):
        return 0.0
    eigvals, eigvecs = np.linalg.eigh(cov)
    major = eigvecs[:, int(np.argmax(eigvals))]
    return float(math.atan2(float(major[1]), float(major[0])))


def _rotation(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, s], [-s, c]], dtype=np.float64)


@dataclass(slots=True)
class _Band:
    lo: float
    hi: float

    @property
    def center(self) -> float:
        return 0.5 * (self.lo + self.hi)

    @property
    def width(self) -> float:
        return self.hi - self.lo


@dataclass(slots=True)
class _PlaneCluster:
    """A vertical rack-face plane in aisle-aligned UV coordinates."""

    v: float
    u_lo: float
    u_hi: float
    z_lo: float
    z_hi: float
    support_points: int
    residual_m: float
    source: str = "vertical_plane_edges"

    @property
    def span_u(self) -> float:
        return self.u_hi - self.u_lo


def _density_bands(
    coord: np.ndarray,
    *,
    res: float,
    occupied: bool,
    min_width: float,
    occ_threshold: float,
) -> list[_Band]:
    """Return contiguous bands along ``coord`` that are occupied/free.

    A 1-D histogram is thresholded; ``scipy.ndimage.label`` groups contiguous
    runs. ``occupied=True`` keeps high-density runs (rack rows); ``occupied=False``
    keeps low-density runs (aisles).
    """
    lo = float(coord.min())
    hi = float(coord.max())
    if hi - lo < res:
        return []
    nbins = max(4, math.ceil((hi - lo) / res))
    hist, edges = np.histogram(coord, bins=nbins, range=(lo, hi))
    peak = float(hist.max()) if hist.size else 0.0
    if peak <= 0:
        return []
    norm = hist.astype(np.float64) / peak
    selector = norm >= occ_threshold if occupied else norm < occ_threshold
    labels, count = ndimage.label(selector)
    bands: list[_Band] = []
    for label_id in range(1, count + 1):
        idx = np.flatnonzero(labels == label_id)
        band = _Band(lo=float(edges[idx[0]]), hi=float(edges[idx[-1] + 1]))
        if band.width >= min_width:
            bands.append(band)
    return bands


def _clean_template_levels(raw_levels: tuple[float, ...]) -> tuple[float, ...]:
    levels: list[float] = []
    for raw in raw_levels or ():
        try:
            level = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(level) and level >= 0.0:
            levels.append(level)
    return tuple(sorted(set(levels))[:12])


def _extract_vertical_plane_rows(
    *,
    u_all: np.ndarray,
    v_all: np.ndarray,
    z_all: np.ndarray,
    params: StructureExtractionParams,
) -> tuple[list[_Band], list[_PlaneCluster], bool]:
    """Detect rack rows from vertical face plane pairs.

    The old extractor treated dense cross-axis bands as rack rows. This keeps
    that as a fallback, but the primary signal is now the pair of boundary
    planes around each occupied rack row. That gives every row explicit face
    plane evidence and a residual instead of a bare 1-D density band.
    """
    density_rows = _density_bands(
        v_all,
        res=params.grid_res_m,
        occupied=True,
        min_width=params.grid_res_m * 2,
        occ_threshold=0.18,
    )
    plane_rows: list[_Band] = []
    planes: list[_PlaneCluster] = []
    for row in density_rows:
        in_row = (v_all >= row.lo) & (v_all <= row.hi)
        if int(in_row.sum()) < 30:
            continue
        row_v = v_all[in_row].astype(np.float64)
        row_u = u_all[in_row].astype(np.float64)
        row_z = z_all[in_row].astype(np.float64)
        lo_plane_v = float(np.percentile(row_v, 8.0))
        hi_plane_v = float(np.percentile(row_v, 92.0))
        if hi_plane_v - lo_plane_v < params.grid_res_m:
            continue
        row_planes: list[_PlaneCluster] = []
        for plane_v in (lo_plane_v, hi_plane_v):
            distances = np.abs(row_v - plane_v)
            near = distances <= max(params.grid_res_m * 1.5, 0.12)
            if not near.any():
                near = distances <= float(np.percentile(distances, 20.0))
            if int(near.sum()) < 12:
                continue
            row_planes.append(
                _PlaneCluster(
                    v=plane_v,
                    u_lo=float(np.percentile(row_u[near], 2.0)),
                    u_hi=float(np.percentile(row_u[near], 98.0)),
                    z_lo=float(np.percentile(row_z[near], 2.0)),
                    z_hi=float(np.percentile(row_z[near], 98.0)),
                    support_points=int(near.sum()),
                    residual_m=float(np.median(distances[near])),
                )
            )
        if len(row_planes) < 2:
            continue
        planes.extend(row_planes)
        plane_rows.append(_Band(lo=min(p.v for p in row_planes), hi=max(p.v for p in row_planes)))

    if plane_rows:
        return plane_rows, planes, False
    return density_rows, [], True


def _plane_for_face(face: dict[str, Any], planes: list[_PlaneCluster]) -> _PlaneCluster | None:
    if not planes:
        return None
    face_v = float(face["face_v"])
    return min(planes, key=lambda plane: abs(float(plane.v) - face_v))


def _upright_bays(
    *,
    u_row: np.ndarray,
    z_row: np.ndarray,
    params: StructureExtractionParams,
) -> list[_Band]:
    """Detect rack bays from repeated vertical upright/support concentrations."""
    if u_row.size < 30:
        return []
    u_min = float(u_row.min())
    u_max = float(u_row.max())
    span = u_max - u_min
    if span < params.min_rack_length_m:
        return []
    nbins = max(6, math.ceil(span / max(params.grid_res_m, 0.05)))
    hist, edges = np.histogram(u_row, bins=nbins, range=(u_min, u_max))
    if hist.max() <= 0:
        return []
    smooth = ndimage.gaussian_filter1d(hist.astype(np.float64), sigma=1.0)
    threshold = max(float(smooth.mean() + smooth.std() * 0.35), float(smooth.max()) * 0.35)
    peak_idx: list[int] = []
    for index in range(1, len(smooth) - 1):
        if (
            smooth[index] >= threshold
            and smooth[index] >= smooth[index - 1]
            and smooth[index] >= smooth[index + 1]
        ):
            peak_idx.append(index)
    if len(peak_idx) < 2:
        return []
    upright_u = [float((edges[index] + edges[index + 1]) * 0.5) for index in peak_idx]
    filtered: list[float] = []
    for value in upright_u:
        if not filtered or abs(value - filtered[-1]) >= max(params.min_rack_length_m * 0.4, 0.25):
            filtered.append(value)
    if len(filtered) < 2:
        return []
    bays: list[_Band] = []
    for left, right in zip(filtered, filtered[1:], strict=False):
        if right - left >= params.min_rack_length_m:
            bays.append(_Band(lo=left, hi=right))
    if not bays:
        return []
    # Avoid a common failure mode where dense shelf clutter creates too many tiny bays.
    if len(bays) > params.max_bins_per_rack_face:
        return []
    return bays


def _shelf_confidence_breakdown(
    *,
    levels: list[float],
    z_points: np.ndarray,
    params: StructureExtractionParams,
) -> dict[str, float]:
    if not levels:
        return {"horizontal_plane_support": 0.0, "pitch_prior": 0.0, "geometry": 0.0}
    support_scores: list[float] = []
    for level in levels:
        near = np.abs(z_points.astype(np.float64) - float(level)) <= max(params.grid_res_m, 0.08)
        support_scores.append(max(0.0, min(1.0, float(near.sum()) / 50.0)))
    pitch_score = 1.0
    if len(levels) > 1:
        gaps = np.diff(sorted(float(level) for level in levels))
        expected = max(params.shelf_min_spacing_m, 1e-6)
        residual = float(np.median(np.abs(gaps - expected)))
        pitch_score = _score_from_residual(residual, good_m=0.08, bad_m=max(0.35, expected))
    support = _confidence_mean(support_scores)
    return {
        "horizontal_plane_support": support,
        "pitch_prior": round(pitch_score, 3),
        "geometry": _confidence_mean([support, pitch_score]),
    }


def _occupancy_aisle_graph_summary(
    occupancy_grid: OccupancyGrid | None,
    *,
    z_m: float,
) -> dict[str, Any] | None:
    if occupancy_grid is None or occupancy_grid.width <= 0 or occupancy_grid.height <= 0:
        return None
    free_cells: list[tuple[int, int]] = []
    for cell in occupancy_grid.iter_cells():
        if str(cell.state).split(".")[-1].lower() == "free":
            free_cells.append((int(cell.x_idx), int(cell.y_idx)))
    if not free_cells:
        return None
    by_y: dict[int, list[int]] = {}
    for x_idx, y_idx in free_cells:
        by_y.setdefault(y_idx, []).append(x_idx)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    aisle_idx = 0
    for y_idx, xs in sorted(by_y.items()):
        xs = sorted(xs)
        runs: list[tuple[int, int]] = []
        start = prev = xs[0]
        for x_idx in xs[1:]:
            if x_idx == prev + 1:
                prev = x_idx
                continue
            runs.append((start, prev))
            start = prev = x_idx
        runs.append((start, prev))
        for start, end in runs:
            if end - start < 2:
                continue
            aisle_idx += 1
            start_pose = occupancy_grid.cell_to_pose(
                start,
                y_idx,
                z_m=z_m,
                frame_id=WAREHOUSE_MAP_FRAME_ID,
            )
            end_pose = occupancy_grid.cell_to_pose(
                end,
                y_idx,
                z_m=z_m,
                frame_id=WAREHOUSE_MAP_FRAME_ID,
            )
            start_id = f"OG{aisle_idx}:start"
            end_id = f"OG{aisle_idx}:end"
            nodes.extend(
                [
                    {
                        "id": start_id,
                        "x_m": round(start_pose.x_m, 3),
                        "y_m": round(start_pose.y_m, 3),
                    },
                    {
                        "id": end_id,
                        "x_m": round(end_pose.x_m, 3),
                        "y_m": round(end_pose.y_m, 3),
                    },
                ]
            )
            edges.append(
                {
                    "from": start_id,
                    "to": end_id,
                    "length_m": round(start_pose.planar_distance_to(end_pose), 3),
                    "source": "occupancy_free_space",
                    "confidence": 1.0,
                }
            )
    if not edges:
        return None
    return {"source": "occupancy_free_space", "nodes": nodes, "edges": edges}


# --------------------------------------------------------------------------- #
# Top-level extraction
# --------------------------------------------------------------------------- #
def extract_structure(
    cloud_xyz: np.ndarray,
    *,
    params: StructureExtractionParams,
    occupancy_grid: OccupancyGrid | None = None,
) -> StructureResult:
    """Run stages A-D on a merged cloud and return targets + summary."""
    params = params.sanitized()
    if cloud_xyz.shape[0] < 50:
        raise StructureExtractionError("Cloud too small for structure extraction.")

    z = cloud_xyz[:, 2]
    floor_z = _detect_floor_z(z, params.grid_res_m)
    band_lo = floor_z + params.floor_margin_m
    band_hi = floor_z + params.ceiling_max_m
    band_hi = min(band_hi, float(np.percentile(z, 99.0)))
    if band_hi <= band_lo:
        band_hi = band_lo + max(params.shelf_min_spacing_m, 0.5)

    keep = (z >= band_lo) & (z <= band_hi)
    rack_mass = cloud_xyz[keep]
    if rack_mass.shape[0] < 50:
        raise StructureExtractionError(
            "No vertical structure remained after floor/ceiling removal."
        )

    xy = rack_mass[:, :2].astype(np.float64)
    if params.axis_deg is not None:
        theta = math.radians(float(params.axis_deg))
    else:
        theta = _dominant_axis_rad(xy)
    rot = _rotation(theta)
    uv = xy @ rot.T  # columns: u (along aisle), v (cross aisle)
    u_all = uv[:, 0]
    v_all = uv[:, 1]

    # Primary core: vertical rack face planes clustered into rack rows. The
    # density-band extractor remains as a review-only fallback for weak scans.
    rack_rows, plane_clusters, used_density_fallback = _extract_vertical_plane_rows(
        u_all=u_all,
        v_all=v_all,
        z_all=rack_mass[:, 2],
        params=params,
    )
    if not rack_rows:
        raise StructureExtractionError("No rack face planes or fallback rack rows detected.")

    aisles = _density_bands(
        v_all,
        res=params.grid_res_m,
        occupied=False,
        min_width=params.min_aisle_width_m,
        occ_threshold=0.18,
    )

    inv_rot = rot.T  # maps (u, v) back to world XY

    def _uv_to_world(u: float, v: float) -> tuple[float, float]:
        world = inv_rot @ np.array([u, v], dtype=np.float64)
        return float(world[0]), float(world[1])

    # KD-tree over the rack mass for the clearance gate (XY+Z).
    clearance_tree = cKDTree(rack_mass.astype(np.float64))

    result = StructureResult(point_count=int(cloud_xyz.shape[0]))
    aisle_summaries: list[dict[str, Any]] = []
    rack_summaries: list[dict[str, Any]] = []

    # Aisle centerlines (summary + code lookup).
    aisle_centers: list[float] = [a.center for a in aisles]
    for a_idx, aisle in enumerate(aisles):
        x0, y0 = _uv_to_world(float(u_all.min()), aisle.center)
        x1, y1 = _uv_to_world(float(u_all.max()), aisle.center)
        aisle_summaries.append(
            {
                "code": f"A{a_idx + 1}",
                "centerline_world": [x0, y0, x1, y1],
                "width_m": round(aisle.width, 3),
                "z_min": round(band_lo, 3),
                "z_max": round(band_hi, 3),
                "confidence_breakdown": _aisle_confidence_breakdown(
                    aisle=aisle,
                    min_aisle_width_m=params.min_aisle_width_m,
                ),
            }
        )

    rack_index = 0
    for row in rack_rows:
        in_row = (v_all >= row.lo) & (v_all <= row.hi)
        if int(in_row.sum()) < 30:
            continue
        u_row = u_all[in_row]
        z_row = rack_mass[in_row, 2]

        # Stage C: split the rack row into bays along the aisle axis.
        bay_source = "density_fallback"
        if params.rack_template_bay_width_m is not None:
            bays = _template_bays(
                u_min=float(u_row.min()),
                u_max=float(u_row.max()),
                bay_width_m=float(params.rack_template_bay_width_m),
                min_rack_length_m=float(params.min_rack_length_m),
            )
            bay_source = "template"
        else:
            bays = _upright_bays(u_row=u_row, z_row=z_row, params=params)
            if bays:
                bay_source = "upright_pitch"
            if not bays:
                bays = _density_bands(
                    u_row,
                    res=params.grid_res_m,
                    occupied=True,
                    min_width=params.min_rack_length_m,
                    occ_threshold=0.12,
                )
                bay_source = "density_fallback"
        if not bays:
            bays = [_Band(lo=float(u_row.min()), hi=float(u_row.max()))]
            bay_source = "whole_row_fallback"

        # Which aisle(s) border this rack row -> face normals point into them.
        faces = _aisle_faces_for_row(row, aisle_centers)
        if not faces:
            continue

        for bay in bays:
            rack_index += 1
            rack_code = f"R{rack_index}"
            in_bay = (u_row >= bay.lo) & (u_row <= bay.hi)
            z_bay = z_row[in_bay]
            if z_bay.size < 20:
                continue

            shelf_levels = (
                list(params.rack_template_shelf_levels_m)
                if params.rack_template_shelf_levels_m
                else _detect_shelf_levels(
                    z_bay,
                    spacing=params.shelf_min_spacing_m,
                    res=params.grid_res_m,
                    max_levels=params.max_shelf_levels,
                )
            )
            if not shelf_levels:
                shelf_levels = [float(np.median(z_bay))]
            shelf_confidence = _shelf_confidence_breakdown(
                levels=shelf_levels,
                z_points=z_bay,
                params=params,
            )

            # Rack bbox (world) for the summary / overlays.
            cx, cy = _uv_to_world(bay.center, row.center)
            template_fit = _template_fit_metrics(
                bay=bay,
                shelf_levels=shelf_levels,
                params=params,
            )
            face_planes = []
            for face in faces:
                plane_cluster = _plane_for_face(face, plane_clusters)
                face_planes.append(
                    _rack_face_plane_summary(
                        u_row=u_row,
                        v_row=v_all[in_row],
                        z_row=z_row,
                        bay=bay,
                        face=face,
                        uv_to_world=_uv_to_world,
                        plane_cluster=plane_cluster,
                        fallback=used_density_fallback,
                    )
                )
            rack_summaries.append(
                {
                    "code": rack_code,
                    "row_v": round(row.center, 3),
                    "center_world": [round(cx, 3), round(cy, 3), round(float(np.median(z_bay)), 3)],
                    "length_m": round(bay.width, 3),
                    "depth_m": round(row.width, 3),
                    "z_min": round(float(z_bay.min()), 3),
                    "z_max": round(float(z_bay.max()), 3),
                    "faces": [f["aisle_code"] for f in faces],
                    "face_planes": face_planes,
                    "bay_detection": bay_source,
                    "shelf_detection": {
                        "source": (
                            "rack_template"
                            if params.rack_template_shelf_levels_m
                            else "horizontal_plane_histogram"
                        ),
                        "levels_m": [round(float(level), 3) for level in shelf_levels],
                        "confidence_breakdown": shelf_confidence,
                    },
                    "template_fit": template_fit,
                    "confidence_breakdown": _rack_confidence_breakdown(
                        points=int(z_bay.size),
                        face_planes=face_planes,
                        template_fit=template_fit,
                        shelf_confidence=shelf_confidence,
                        fallback=used_density_fallback,
                    ),
                }
            )

            for face in faces:
                _emit_bay_targets(
                    result=result,
                    params=params,
                    bay=bay,
                    row=row,
                    face=face,
                    shelf_levels=shelf_levels,
                    uv_to_world=_uv_to_world,
                    clearance_tree=clearance_tree,
                    occupancy_grid=occupancy_grid,
                    rack_code=rack_code,
                    face_plane=next(
                        (
                            plane
                            for plane in face_planes
                            if plane.get("aisle_code") == face.get("aisle_code")
                        ),
                        None,
                    ),
                    template_fit=template_fit,
                )

    if not result.targets and not rack_summaries:
        raise StructureExtractionError("No usable rack structure was detected.")

    if occupancy_grid is not None:
        _assign_astar_priority(
            result.targets,
            occupancy_grid=occupancy_grid,
            clearance_m=params.required_clearance_m,
        )
    else:
        _assign_serpentine_priority(result.targets)

    if used_density_fallback:
        for target in result.targets:
            if target.clearance_status == "active":
                target.clearance_status = "needs_review"
            target.confidence_breakdown["fallback_extractor"] = 0.25
            target.confidence = _confidence_mean(list(target.confidence_breakdown.values()))

    target_counts = {
        "candidate": len(result.targets),
        "active": sum(target.clearance_status == "active" for target in result.targets),
        "needs_review": sum(target.clearance_status == "needs_review" for target in result.targets),
        "rejected": sum(target.clearance_status == "rejected" for target in result.targets),
    }
    occupancy_graph = _occupancy_aisle_graph_summary(occupancy_grid, z_m=band_lo)
    density_graph = _aisle_graph_summary(
        aisles,
        u_min=float(u_all.min()),
        u_max=float(u_all.max()),
        min_aisle_width_m=params.min_aisle_width_m,
    )
    result.summary = {
        "status": "ready" if target_counts["active"] > 0 else "degraded",
        "coordinate_setup_status": ("active" if target_counts["active"] > 0 else "draft"),
        "manual_review_required": target_counts["needs_review"] > 0 or target_counts["active"] == 0,
        "frame_id": WAREHOUSE_MAP_FRAME_ID,
        "floor_z": round(floor_z, 3),
        "axis_deg": round(math.degrees(theta), 2),
        "height_band_m": [round(band_lo, 3), round(band_hi, 3)],
        "algorithm_core": {
            "primary": "vertical_plane_graph",
            "fallback_used": bool(used_density_fallback),
            "plane_cluster_count": len(plane_clusters),
            "row_source": "density_fallback" if used_density_fallback else "parallel_face_planes",
        },
        "rack_plane_clusters": [
            {
                "v_m": round(plane.v, 3),
                "u_range_m": [round(plane.u_lo, 3), round(plane.u_hi, 3)],
                "z_range_m": [round(plane.z_lo, 3), round(plane.z_hi, 3)],
                "support_points": plane.support_points,
                "residual_m": round(plane.residual_m, 4),
                "source": plane.source,
            }
            for plane in plane_clusters
        ],
        "aisles": aisle_summaries,
        "aisle_graph": occupancy_graph or density_graph,
        "racks": rack_summaries,
        "counts": {
            "aisles": len(aisle_summaries),
            "racks": len(rack_summaries),
            "targets": len(result.targets),
            "active_targets": target_counts["active"],
            "review_targets": target_counts["needs_review"],
            "candidate_targets": target_counts["candidate"],
            "rejected_clearance": result.rejected_clearance,
        },
        "target_counts": target_counts,
        "candidate_targets": [_target_summary(target) for target in result.targets],
        "active_targets": [
            _target_summary(target)
            for target in result.targets
            if target.clearance_status == "active"
        ],
        "review_targets": [
            _target_summary(target)
            for target in result.targets
            if target.clearance_status == "needs_review"
        ],
        "rejected_targets": [
            _target_summary(target)
            for target in result.targets
            if target.clearance_status == "rejected"
        ],
        "params": _params_to_dict(params),
        "clearance": {
            "source": "occupancy_grid" if occupancy_grid is not None else "point_cloud_kdtree",
            "required_clearance_m": round(params.required_clearance_m, 3),
        },
        "warnings": (
            (
                ["Structure detected but all scan targets failed the clearance gate."]
                if target_counts["active"] == 0
                else []
            )
            + (
                ["Plane evidence was weak; PCA/density fallback outputs require review."]
                if used_density_fallback and result.targets
                else []
            )
        ),
        "rejection_diagnostics": result.rejection_diagnostics,
        "routing": {
            "mode": "occupancy_astar" if occupancy_grid is not None else "aisle_serpentine",
            "source": (
                "persisted_occupancy_grid" if occupancy_grid is not None else "geometry_ordering"
            ),
        },
    }
    return result


def _aisle_faces_for_row(
    row: _Band,
    aisle_centers: list[float],
) -> list[dict[str, Any]]:
    """Return the rack face(s): each adjacent aisle gives a face plane + normal.

    ``face_v`` is the rack edge facing the aisle; ``sign`` is the v-direction the
    drone approaches from (toward the aisle).
    """
    faces: list[dict[str, Any]] = []
    for a_idx, center in enumerate(aisle_centers):
        code = f"A{a_idx + 1}"
        if center > row.hi:
            # Aisle on the +v side; rack face is row.hi, normal points +v.
            faces.append(
                {"face_v": row.hi, "sign": 1.0, "aisle_code": code, "gap": center - row.hi}
            )
        elif center < row.lo:
            faces.append(
                {"face_v": row.lo, "sign": -1.0, "aisle_code": code, "gap": row.lo - center}
            )
    # Keep only the nearest aisle on each side to avoid duplicate faces.
    nearest: dict[float, dict[str, Any]] = {}
    for face in faces:
        key = face["sign"]
        if key not in nearest or face["gap"] < nearest[key]["gap"]:
            nearest[key] = face
    return list(nearest.values())


def _template_bays(
    *,
    u_min: float,
    u_max: float,
    bay_width_m: float,
    min_rack_length_m: float,
) -> list[_Band]:
    span = max(0.0, float(u_max) - float(u_min))
    width = max(float(min_rack_length_m), float(bay_width_m))
    if span <= 0.0 or width <= 0.0:
        return []
    count = max(1, round(span / width))
    actual = span / count
    return [
        _Band(lo=float(u_min) + index * actual, hi=float(u_min) + (index + 1) * actual)
        for index in range(count)
        if actual >= min_rack_length_m
    ]


def _score_from_residual(residual_m: float | None, *, good_m: float, bad_m: float) -> float:
    if residual_m is None or not math.isfinite(float(residual_m)):
        return 0.5
    value = float(residual_m)
    if value <= good_m:
        return 1.0
    if value >= bad_m:
        return 0.0
    return max(0.0, min(1.0, 1.0 - ((value - good_m) / (bad_m - good_m))))


def _confidence_mean(values: list[float]) -> float:
    if not values:
        return 0.5
    clean = [max(0.0, min(1.0, float(value))) for value in values if math.isfinite(float(value))]
    return round(sum(clean) / len(clean), 3) if clean else 0.5


def _aisle_confidence_breakdown(*, aisle: _Band, min_aisle_width_m: float) -> dict[str, float]:
    width_ratio = float(aisle.width) / max(float(min_aisle_width_m), 1e-6)
    width_score = max(0.0, min(1.0, width_ratio))
    return {
        "width": round(width_score, 3),
        "geometry": round(width_score, 3),
    }


def _rack_face_plane_summary(
    *,
    u_row: np.ndarray,
    v_row: np.ndarray,
    z_row: np.ndarray,
    bay: _Band,
    face: dict[str, Any],
    uv_to_world,
    plane_cluster: _PlaneCluster | None = None,
    fallback: bool = False,
) -> dict[str, Any]:
    in_bay = (u_row >= bay.lo) & (u_row <= bay.hi)
    candidates = v_row[in_bay]
    z_candidates = z_row[in_bay]
    face_v = float(plane_cluster.v) if plane_cluster is not None else float(face["face_v"])
    if plane_cluster is not None:
        residual = float(plane_cluster.residual_m)
        points = int(plane_cluster.support_points)
    elif candidates.size == 0:
        residual = None
        points = 0
    else:
        distances = np.abs(candidates.astype(np.float64) - face_v)
        near = distances <= max(0.20, float(bay.width) * 0.05)
        if not near.any():
            near = distances <= float(np.percentile(distances, 25.0))
        residual = float(np.median(distances[near])) if near.any() else float(np.median(distances))
        points = int(near.sum()) if near.any() else int(candidates.size)
    x0, y0 = uv_to_world(bay.lo, face_v)
    x1, y1 = uv_to_world(bay.hi, face_v)
    return {
        "aisle_code": str(face.get("aisle_code") or ""),
        "plane_kind": "vertical_rack_face",
        "line_world": [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)],
        "residual_rms_m": None if residual is None else round(residual, 4),
        "support_points": points,
        "z_min": None if z_candidates.size == 0 else round(float(z_candidates.min()), 3),
        "z_max": None if z_candidates.size == 0 else round(float(z_candidates.max()), 3),
        "source": "density_fallback" if fallback else "vertical_plane_extraction",
        "confidence": round(_score_from_residual(residual, good_m=0.04, bad_m=0.25), 3),
    }


def _template_fit_metrics(
    *,
    bay: _Band,
    shelf_levels: list[float],
    params: StructureExtractionParams,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {"applied": False}
    scores: list[float] = []
    if params.rack_template_bay_width_m is not None:
        width = float(params.rack_template_bay_width_m)
        residual = abs(float(bay.width) - width)
        metrics.update(
            {
                "applied": True,
                "bay_width_m": round(width, 3),
                "bay_width_residual_m": round(residual, 4),
            }
        )
        scores.append(_score_from_residual(residual, good_m=0.03, bad_m=max(0.25, width * 0.25)))
    if params.rack_template_shelf_levels_m:
        expected = list(params.rack_template_shelf_levels_m)
        paired = zip(sorted(shelf_levels), expected, strict=False)
        residuals = [abs(float(left) - float(right)) for left, right in paired]
        residual = max(residuals) if residuals else None
        metrics.update(
            {
                "applied": True,
                "shelf_levels_m": [round(float(value), 3) for value in expected],
                "shelf_level_residual_m": None if residual is None else round(residual, 4),
            }
        )
        scores.append(_score_from_residual(residual, good_m=0.03, bad_m=0.20))
    if params.rack_template_bin_count is not None:
        metrics.update(
            {
                "applied": True,
                "bin_count": int(params.rack_template_bin_count),
            }
        )
        scores.append(1.0)
    metrics["confidence"] = _confidence_mean(scores) if scores else 0.5
    return metrics


def _rack_confidence_breakdown(
    *,
    points: int,
    face_planes: list[dict[str, Any]],
    template_fit: dict[str, Any],
    shelf_confidence: dict[str, float] | None = None,
    fallback: bool = False,
) -> dict[str, float]:
    point_score = max(0.0, min(1.0, float(points) / 500.0))
    plane_scores = [
        float(face.get("confidence"))
        for face in face_planes
        if isinstance(face.get("confidence"), (int, float))
    ]
    plane_score = _confidence_mean(plane_scores)
    template_score = float(template_fit.get("confidence") or 0.5)
    shelf_score = (
        float(shelf_confidence.get("geometry"))
        if isinstance(shelf_confidence, dict)
        and isinstance(shelf_confidence.get("geometry"), (int, float))
        else 0.5
    )
    fallback_score = 0.25 if fallback else 1.0
    return {
        "point_support": round(point_score, 3),
        "rack_face_plane": round(plane_score, 3),
        "shelf_planes": round(max(0.0, min(1.0, shelf_score)), 3),
        "template_fit": round(max(0.0, min(1.0, template_score)), 3),
        "fallback_extractor": fallback_score,
        "geometry": _confidence_mean(
            [point_score, plane_score, template_score, shelf_score, fallback_score]
        ),
    }


def _target_confidence_breakdown(
    *,
    clearance_status: str,
    clearance_source: str,
    face_plane: dict[str, Any] | None,
    template_fit: dict[str, Any] | None,
) -> dict[str, float]:
    clearance_score = (
        1.0
        if clearance_status == "active"
        else 0.65
        if clearance_status == "needs_review"
        else 0.2
    )
    evidence_score = 1.0 if clearance_source == "occupancy_grid" else 0.55
    plane_score = (
        float(face_plane.get("confidence"))
        if isinstance(face_plane, dict) and isinstance(face_plane.get("confidence"), (int, float))
        else 0.5
    )
    template_score = (
        float(template_fit.get("confidence"))
        if isinstance(template_fit, dict)
        and isinstance(template_fit.get("confidence"), (int, float))
        else 0.5
    )
    return {
        "clearance": round(clearance_score, 3),
        "clearance_evidence": round(evidence_score, 3),
        "rack_face_plane": round(max(0.0, min(1.0, plane_score)), 3),
        "template_fit": round(max(0.0, min(1.0, template_score)), 3),
    }


def _scanner_standoff_m(params: StructureExtractionParams) -> float:
    horizontal_fov_deg = 70.0
    barcode_width_m = 0.08
    roi_width_fraction = 0.50
    fov_width_m_at_1m = 2.0 * math.tan(math.radians(horizontal_fov_deg) * 0.5)
    min_barcode_fit_m = barcode_width_m / max(roi_width_fraction * fov_width_m_at_1m, 1e-6)
    downwash_standoff_m = float(params.drone_radius_m) + max(float(params.clearance_margin_m), 0.20)
    return round(max(float(params.standoff_m), min_barcode_fit_m, downwash_standoff_m), 3)


def _scanner_metadata(
    *,
    target_point: WarehouseLocalPoint,
    shelf_normal: WarehouseShelfNormal,
    standoff_m: float,
    params: StructureExtractionParams,
    template_fit: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "barcode_mode": "decode" if params.barcode_scan_expected else "decode_if_present",
        "empty_bin_vision_mode": "classify_empty_bin",
        "expected_sku": None,
        "expected_barcode": None,
        "image_roi": {
            "mode": "center_crop",
            "x": 0.25,
            "y": 0.20,
            "width": 0.50,
            "height": 0.60,
        },
        "min_confidence": 0.75,
        "scanner_fov_deg": {"horizontal": 70.0, "vertical": 45.0},
        "barcode_expected_size_m": {"width": 0.08, "height": 0.03},
        "lighting_constraints": {
            "min_lux": 100.0,
            "avoid_glare": True,
            "preferred_incidence_deg": 0.0,
            "max_incidence_deg": 25.0,
        },
        "target_point_local_json": target_point.model_dump(),
        "shelf_normal_local_json": shelf_normal.model_dump(),
        "standoff_m": float(standoff_m),
        "drone_radius_m": float(params.drone_radius_m),
        "downwash_margin_m": max(float(params.clearance_margin_m), 0.20),
        "template_fit": dict(template_fit or {}),
    }


def _angle_between_deg(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    ax, ay, az = a
    bx, by, bz = b
    denom = math.sqrt(ax * ax + ay * ay + az * az) * math.sqrt(bx * bx + by * by + bz * bz)
    if denom <= 1e-9:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (ax * bx + ay * by + az * bz) / denom))))


def _scan_pose_validation(
    *,
    target_point: WarehouseLocalPoint,
    shelf_normal: WarehouseShelfNormal,
    scan_pose: Any,
    clearance_m: float,
    clearance_source: str,
    occupancy_grid: OccupancyGrid | None,
    params: StructureExtractionParams,
) -> tuple[dict[str, Any], str | None]:
    required_clearance_m = float(params.required_clearance_m)
    pose = LocalPose(
        x_m=float(scan_pose.x_m),
        y_m=float(scan_pose.y_m),
        z_m=float(scan_pose.z_m),
        yaw_deg=float(scan_pose.yaw_deg or 0.0),
        frame_id=str(scan_pose.frame_id),
    )
    target_vector = (
        float(target_point.x_m) - pose.x_m,
        float(target_point.y_m) - pose.y_m,
        float(target_point.z_m) - pose.z_m,
    )
    normal_vector = (float(shelf_normal.x), float(shelf_normal.y), float(shelf_normal.z))
    approach_angle_deg = _angle_between_deg(target_vector, normal_vector)
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not 0.25 <= pose.z_m <= float(params.ceiling_max_m):
        failures.append(
            {
                "check": "altitude",
                "message": "Scan pose is outside altitude envelope",
                "z_m": round(pose.z_m, 3),
            }
        )
    if approach_angle_deg > 25.0:
        failures.append(
            {
                "check": "approach_cone",
                "message": "Scan pose does not face the rack normal",
                "angle_deg": round(approach_angle_deg, 3),
            }
        )
    if clearance_m < required_clearance_m:
        failures.append(
            {
                "check": "clearance",
                "message": "Scan pose violates drone radius/downwash clearance",
                "clearance_m": round(float(clearance_m), 3),
                "required_m": round(required_clearance_m, 3),
                "source": clearance_source,
            }
        )

    path_summary: dict[str, Any] = {
        "dock_reference": "map_origin_nearest_free",
        "required_clearance_m": round(required_clearance_m, 3),
    }
    if occupancy_grid is None:
        warnings.append(
            {
                "check": "esdf_occupancy",
                "message": "No ESDF or occupancy grid was available during generation",
            }
        )
        path_summary.update({"status": "needs_review", "reason": "path_validation_requires_grid"})
    else:
        dock_pose = LocalPose(
            x_m=float(occupancy_grid.origin_x_m),
            y_m=float(occupancy_grid.origin_y_m),
            z_m=pose.z_m,
            frame_id=pose.frame_id,
        )
        outbound = occupancy_grid.astar_path(dock_pose, pose, clearance_m=required_clearance_m)
        inbound = occupancy_grid.astar_path(pose, dock_pose, clearance_m=required_clearance_m)
        if not outbound or not inbound:
            failures.append(
                {
                    "check": "swept_path",
                    "message": "No collision-free inflated round trip exists",
                    "outbound_samples": len(outbound),
                    "return_samples": len(inbound),
                }
            )
            path_summary.update({"status": "rejected", "reason": "swept_path_unreachable"})
        else:
            path_summary.update(
                {
                    "status": "active",
                    "outbound_samples": len(outbound),
                    "return_samples": len(inbound),
                    "outbound_length_m": round(occupancy_grid.path_length_m(outbound), 3),
                    "return_length_m": round(occupancy_grid.path_length_m(inbound), 3),
                }
            )
        path_summary["pose_cell"] = list(occupancy_grid.world_to_cell(pose))

    esdf_summary = {
        "status": "fallback_used" if occupancy_grid is not None else "unavailable",
        "source": "occupancy_grid" if occupancy_grid is not None else None,
    }
    validation = {
        "status": "rejected" if failures else path_summary.get("status", "active"),
        "esdf": esdf_summary,
        "scan_pose": {
            "approach_angle_deg": round(approach_angle_deg, 3),
            "clearance_m": round(float(clearance_m), 3),
            "clearance_source": clearance_source,
        },
        "path": path_summary,
        "warnings": warnings,
        "failures": failures,
    }
    reason = None
    if failures:
        reason = str(failures[0].get("check") or "scan_pose_validation_failed")
    elif path_summary.get("status") != "active":
        reason = str(path_summary.get("reason") or "path_validation_needs_review")
    return validation, reason


def _aisle_graph_summary(
    aisles: list[_Band],
    *,
    u_min: float,
    u_max: float,
    min_aisle_width_m: float,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    length = max(0.0, float(u_max) - float(u_min))
    for index, aisle in enumerate(aisles, start=1):
        start_id = f"A{index}:start"
        end_id = f"A{index}:end"
        nodes.extend(
            [
                {
                    "id": start_id,
                    "aisle_code": f"A{index}",
                    "u_m": round(u_min, 3),
                    "v_m": round(aisle.center, 3),
                },
                {
                    "id": end_id,
                    "aisle_code": f"A{index}",
                    "u_m": round(u_max, 3),
                    "v_m": round(aisle.center, 3),
                },
            ]
        )
        edges.append(
            {
                "from": start_id,
                "to": end_id,
                "length_m": round(length, 3),
                "width_m": round(aisle.width, 3),
                "source": "density_free_space",
                "confidence": _aisle_confidence_breakdown(
                    aisle=aisle,
                    min_aisle_width_m=min_aisle_width_m,
                )["geometry"],
            }
        )
    return {"source": "density_free_space", "nodes": nodes, "edges": edges}


def _detect_shelf_levels(
    z: np.ndarray,
    *,
    spacing: float,
    res: float,
    max_levels: int,
) -> list[float]:
    """Z-histogram peaks = horizontal shelf beams (regular spacing prior)."""
    z_lo = float(z.min())
    z_hi = float(z.max())
    if z_hi - z_lo < spacing:
        return [0.5 * (z_lo + z_hi)]
    nbins = max(4, math.ceil((z_hi - z_lo) / res))
    hist, edges = np.histogram(z, bins=nbins, range=(z_lo, z_hi))
    if hist.max() <= 0:
        return [0.5 * (z_lo + z_hi)]
    norm = hist.astype(np.float64) / float(hist.max())
    # Minimum index separation between distinct shelves.
    min_sep = max(1, round(spacing / res))
    candidates = [i for i in range(len(norm)) if norm[i] >= 0.45]
    levels: list[float] = []
    last = -min_sep
    for i in candidates:
        if i - last < min_sep:
            # Keep the denser of the two adjacent peaks.
            if levels and norm[i] > norm[last]:
                levels[-1] = float((edges[i] + edges[i + 1]) * 0.5)
                last = i
            continue
        levels.append(float((edges[i] + edges[i + 1]) * 0.5))
        last = i
    if not levels:
        return [0.5 * (z_lo + z_hi)]
    if len(levels) <= max_levels:
        return levels
    # Keep the strongest separated shelf bands instead of every small noisy z peak.
    ranked = sorted(
        levels,
        key=lambda level: hist[min(len(hist) - 1, max(0, int((level - z_lo) / max(res, 1e-6))))],
        reverse=True,
    )[:max_levels]
    return sorted(ranked)


def _emit_bay_targets(
    *,
    result: StructureResult,
    params: StructureExtractionParams,
    bay: _Band,
    row: _Band,
    face: dict[str, Any],
    shelf_levels: list[float],
    uv_to_world,
    clearance_tree: cKDTree,
    occupancy_grid: OccupancyGrid | None,
    rack_code: str,
    face_plane: dict[str, Any] | None = None,
    template_fit: dict[str, Any] | None = None,
) -> None:
    """Stage D: divide a bay face into bins x shelf levels -> scan targets."""
    face_v = float(face["face_v"])
    sign = float(face["sign"])
    aisle_code = str(face["aisle_code"])
    nx, ny = uv_to_world(0.0, sign)  # world direction of +v*sign at origin...
    ox, oy = uv_to_world(0.0, 0.0)
    normal_x = nx - ox
    normal_y = ny - oy
    nlen = math.hypot(normal_x, normal_y)
    if nlen <= 1e-9:
        return
    normal_x /= nlen
    normal_y /= nlen

    if params.rack_template_bin_count is not None:
        n_bins = min(int(params.rack_template_bin_count), params.max_bins_per_rack_face)
    else:
        pitch = max(params.bin_pitch_m, params.min_target_spacing_m, params.grid_res_m * 2)
        n_bins = max(1, round(bay.width / pitch))
        n_bins = min(n_bins, params.max_bins_per_rack_face)
    target_standoff_m = _scanner_standoff_m(params)
    for b_idx in range(n_bins):
        u_center = bay.lo + (b_idx + 0.5) * (bay.width / n_bins)
        for level_idx, z_level in enumerate(shelf_levels):
            tx, ty = uv_to_world(u_center, face_v)
            target_point = WarehouseLocalPoint(
                frame_id=WAREHOUSE_MAP_FRAME_ID, x_m=tx, y_m=ty, z_m=float(z_level)
            )
            shelf_normal = WarehouseShelfNormal(
                frame_id=WAREHOUSE_MAP_FRAME_ID, x=normal_x, y=normal_y, z=0.0
            )
            try:
                scan_pose = compute_scan_pose(
                    target_point=target_point,
                    shelf_normal=shelf_normal,
                    standoff_m=target_standoff_m,
                )
            except ValueError:
                continue

            if occupancy_grid is not None:
                clearance = occupancy_grid.clearance_at(
                    LocalPose(
                        x_m=scan_pose.x_m,
                        y_m=scan_pose.y_m,
                        z_m=scan_pose.z_m,
                        frame_id=scan_pose.frame_id,
                    )
                )
                clearance_source = "occupancy_grid"
            else:
                clearance, _ = clearance_tree.query(
                    np.array([scan_pose.x_m, scan_pose.y_m, scan_pose.z_m], dtype=np.float64)
                )
                clearance_source = "point_cloud_kdtree"
            clearance = float(clearance)
            clearance_status = classify_clearance(
                clearance,
                strict_clearance_m=params.required_clearance_m,
                review_clearance_m=params.review_clearance_m,
                reliable_evidence=occupancy_grid is not None,
            )
            scanner_metadata = _scanner_metadata(
                target_point=target_point,
                shelf_normal=shelf_normal,
                standoff_m=target_standoff_m,
                params=params,
                template_fit=template_fit,
            )
            path_validation, failure_reason = _scan_pose_validation(
                target_point=target_point,
                shelf_normal=shelf_normal,
                scan_pose=scan_pose,
                clearance_m=clearance,
                clearance_source=clearance_source,
                occupancy_grid=occupancy_grid,
                params=params,
            )
            if path_validation.get("status") == "rejected" and clearance_status != "rejected":
                clearance_status = "rejected"
            elif path_validation.get("status") != "active" and clearance_status == "active":
                clearance_status = "needs_review"
            if clearance_status != "active" and failure_reason is None:
                failure_reason = (
                    "clearance_below_required"
                    if clearance_status == "rejected"
                    else "clearance_requires_review"
                )
            confidence_breakdown = _target_confidence_breakdown(
                clearance_status=clearance_status,
                clearance_source=clearance_source,
                face_plane=face_plane,
                template_fit=template_fit,
            )
            confidence = _confidence_mean(list(confidence_breakdown.values()))
            if clearance_status == "rejected":
                result.rejected_clearance += 1
                half = max(params.grid_res_m, 0.05) * 0.5
                rejection_reason = failure_reason or "clearance_below_required"
                result.rejection_diagnostics.append(
                    {
                        "candidate_id": f"{rack_code}:{aisle_code}:B{b_idx + 1}:L{level_idx}",
                        "rejection_reason": rejection_reason,
                        "clearance_m": round(clearance, 3),
                        "required_clearance_m": round(params.required_clearance_m, 3),
                        "path_status": path_validation.get("status"),
                        "bbox": [
                            round(scan_pose.x_m - half, 3),
                            round(scan_pose.y_m - half, 3),
                            round(scan_pose.z_m - half, 3),
                            round(scan_pose.x_m + half, 3),
                            round(scan_pose.y_m + half, 3),
                            round(scan_pose.z_m + half, 3),
                        ],
                        "frame_id": WAREHOUSE_MAP_FRAME_ID,
                    }
                )
            result.targets.append(
                GeneratedTarget(
                    aisle_code=aisle_code,
                    rack_code=rack_code,
                    shelf_level=level_idx,
                    bin_code=f"B{b_idx + 1}",
                    target_point=target_point.model_dump(),
                    shelf_normal=shelf_normal.model_dump(),
                    scan_pose=scan_pose.model_dump(),
                    standoff_m=float(target_standoff_m),
                    priority=100,
                    clearance_status=clearance_status,
                    clearance_m=clearance,
                    clearance_source=clearance_source,
                    confidence=confidence,
                    confidence_breakdown=confidence_breakdown,
                    template_metadata={
                        "template_version_id": params.rack_template_version_id,
                        "template_fit": dict(template_fit or {}),
                        "rack_face_plane": dict(face_plane or {}),
                        "rack_template_bin_count": params.rack_template_bin_count,
                        "rack_template_bay_width_m": params.rack_template_bay_width_m,
                        "rack_template_shelf_levels_m": list(
                            params.rack_template_shelf_levels_m
                        ),
                    },
                    scanner_metadata=scanner_metadata,
                    path_validation=path_validation,
                    failure_reason=failure_reason,
                )
            )


def _target_summary(target: GeneratedTarget) -> dict[str, Any]:
    return {
        "candidate_id": (
            f"{target.rack_code}:{target.aisle_code}:{target.bin_code}:L{target.shelf_level}"
        ),
        "aisle_code": target.aisle_code,
        "rack_code": target.rack_code,
        "shelf_level": target.shelf_level,
        "bin_code": target.bin_code,
        "status": target.clearance_status,
        "clearance_m": (round(target.clearance_m, 3) if target.clearance_m is not None else None),
        "clearance_source": target.clearance_source,
        "confidence": round(float(target.confidence), 3),
        "confidence_breakdown": dict(target.confidence_breakdown),
        "template": dict(target.template_metadata or {}),
        "scanner_metadata": dict(target.scanner_metadata or {}),
        "path_validation": dict(target.path_validation or {}),
        "failure_reason": target.failure_reason,
        "target_point": dict(target.target_point),
        "scan_pose": dict(target.scan_pose),
    }


def _assign_serpentine_priority(targets: list[GeneratedTarget]) -> None:
    """Aisle-aware serpentine ordering -> priority (lower flies first).

    Targets are grouped by aisle, then ordered along the aisle axis, alternating
    direction per aisle (boustrophedon) so the drone does not backtrack the full
    length between aisles. This is the lightweight stand-in for full A* routing.
    """
    by_aisle: dict[str, list[GeneratedTarget]] = {}
    for tgt in targets:
        by_aisle.setdefault(tgt.aisle_code, []).append(tgt)

    priority = 0
    for serpentine_idx, aisle_code in enumerate(sorted(by_aisle)):
        group = by_aisle[aisle_code]
        # Order along the aisle by projecting the target onto its dominant span.
        group.sort(key=lambda t: (t.target_point["x_m"], t.target_point["y_m"], t.shelf_level))
        if serpentine_idx % 2 == 1:
            group.reverse()
        for tgt in group:
            tgt.priority = priority
            priority += 1


def _pose_for_target(target: GeneratedTarget) -> LocalPose:
    pose = target.scan_pose
    return LocalPose(
        x_m=float(pose["x_m"]),
        y_m=float(pose["y_m"]),
        z_m=float(pose.get("z_m", 0.0)),
        yaw_deg=float(pose["yaw_deg"]) if pose.get("yaw_deg") is not None else None,
        frame_id=str(pose.get("frame_id") or WAREHOUSE_MAP_FRAME_ID),
    )


def _assign_astar_priority(
    targets: list[GeneratedTarget],
    *,
    occupancy_grid: OccupancyGrid,
    clearance_m: float,
) -> None:
    """Collision-aware target order using OccupancyGrid.astar_path path length."""
    if len(targets) <= 1:
        _assign_serpentine_priority(targets)
        return

    remaining = sorted(
        targets,
        key=lambda t: (
            str(t.aisle_code),
            str(t.rack_code),
            int(t.shelf_level),
            str(t.bin_code),
        ),
    )
    ordered: list[GeneratedTarget] = [remaining.pop(0)]
    current_pose = _pose_for_target(ordered[0])

    while remaining:
        best_index = 0
        best_cost = float("inf")
        for idx, candidate in enumerate(remaining):
            candidate_pose = _pose_for_target(candidate)
            path = occupancy_grid.astar_path(
                current_pose,
                candidate_pose,
                clearance_m=clearance_m,
            )
            if path:
                cost = occupancy_grid.path_length_m(path)
            else:
                cost = current_pose.planar_distance_to(candidate_pose) + 1_000_000.0
            if cost < best_cost:
                best_index = idx
                best_cost = cost
        selected = remaining.pop(best_index)
        ordered.append(selected)
        current_pose = _pose_for_target(selected)

    for priority, target in enumerate(ordered):
        target.priority = priority


def _params_to_dict(params: StructureExtractionParams) -> dict[str, Any]:
    return {
        "voxel_m": params.voxel_m,
        "grid_res_m": params.grid_res_m,
        "floor_margin_m": params.floor_margin_m,
        "ceiling_max_m": params.ceiling_max_m,
        "min_aisle_width_m": params.min_aisle_width_m,
        "min_rack_length_m": params.min_rack_length_m,
        "bin_pitch_m": params.bin_pitch_m,
        "shelf_min_spacing_m": params.shelf_min_spacing_m,
        "max_shelf_levels": params.max_shelf_levels,
        "max_bins_per_rack_face": params.max_bins_per_rack_face,
        "min_target_spacing_m": params.min_target_spacing_m,
        "review_clearance_m": params.review_clearance_m,
        "standoff_m": params.standoff_m,
        "drone_radius_m": params.drone_radius_m,
        "clearance_margin_m": params.clearance_margin_m,
        "min_surface_points": params.min_surface_points,
        "rack_template_version_id": params.rack_template_version_id,
        "rack_template_bin_count": params.rack_template_bin_count,
        "rack_template_bay_width_m": params.rack_template_bay_width_m,
        "rack_template_shelf_levels_m": list(params.rack_template_shelf_levels_m),
        "axis_deg": params.axis_deg,
    }


def extract_structure_from_flight(
    client_flight_id: str,
    *,
    params: StructureExtractionParams,
    occupancy_grid: OccupancyGrid | None = None,
    odom_to_warehouse_map_transform: dict[str, Any] | None = None,
) -> StructureResult:
    """Convenience entry point: load the flight cloud then run extraction."""
    params = params.sanitized()
    cloud = load_flight_cloud(client_flight_id, params=params)
    if odom_to_warehouse_map_transform is None:
        raise StructureExtractionError("Locked warehouse_map -> odom localization is required")
    cloud = transform_odom_points(cloud, odom_to_warehouse_map_transform).astype(np.float32)
    # OccupancyGrid currently has axis-aligned origin only (no origin yaw). It
    # cannot be safely carried across an arbitrary localization rotation. Use
    # transformed point-cloud clearance until the grid contract supports SE(2).
    occupancy_grid = None
    logger.info(
        "structure_extraction loaded flight=%s points=%s voxel=%.3f occupancy=%s",
        client_flight_id,
        cloud.shape[0],
        params.voxel_m,
        occupancy_grid is not None,
    )
    result = extract_structure(cloud, params=params, occupancy_grid=occupancy_grid)
    result.summary["source_frame_id"] = "odom"
    result.summary["localization_applied"] = True
    clearance = result.summary.get("clearance")
    if isinstance(clearance, dict):
        if occupancy_grid is not None:
            clearance["source"] = "occupancy_grid"
        else:
            try:
                from backend.modules.warehouse.service.live_map_manifest import load_flight_manifest

                manifest = load_flight_manifest(client_flight_id)
                if manifest is not None and not manifest.nvblox_available:
                    clearance["source"] = "point_cloud_fallback"
                    clearance["missing_topics"] = list(manifest.missing_topics or [])
            except Exception:
                logger.debug("structure_extraction_clearance_hints_failed", exc_info=True)
    return result
