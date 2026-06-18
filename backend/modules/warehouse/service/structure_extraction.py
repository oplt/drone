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
* Coordinates stay in the ``warehouse_map`` frame (== ``odom`` from the same
  dock), which is exactly the frame the inspection waypoint builder consumes, so
  detected points are directly flyable.

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
    standoff_m: float = 1.2
    drone_radius_m: float = 0.35
    clearance_margin_m: float = 0.25
    max_points: int = 6_000_000
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
            standoff_m=_pos(self.standoff_m, 1.2),
            drone_radius_m=_pos(self.drone_radius_m, 0.35),
            clearance_margin_m=_pos(self.clearance_margin_m, 0.25, minimum=0.0),
            max_points=max(10_000, int(self.max_points or 6_000_000)),
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


@dataclass(slots=True)
class StructureResult:
    targets: list[GeneratedTarget] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    point_count: int = 0
    rejected_clearance: int = 0


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

    return voxel_downsample(merged, params.voxel_m)


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

    # Cross-axis density: rack rows are dense, aisles are the empty gaps.
    rack_rows = _density_bands(
        v_all,
        res=params.grid_res_m,
        occupied=True,
        min_width=params.grid_res_m * 2,
        occ_threshold=0.18,
    )
    if not rack_rows:
        raise StructureExtractionError("No rack rows detected in cross-axis profile.")

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
        bays = _density_bands(
            u_row,
            res=params.grid_res_m,
            occupied=True,
            min_width=params.min_rack_length_m,
            occ_threshold=0.12,
        )
        if not bays:
            bays = [_Band(lo=float(u_row.min()), hi=float(u_row.max()))]

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

            shelf_levels = _detect_shelf_levels(
                z_bay, spacing=params.shelf_min_spacing_m, res=params.grid_res_m
            )
            if not shelf_levels:
                shelf_levels = [float(np.median(z_bay))]

            # Rack bbox (world) for the summary / overlays.
            cx, cy = _uv_to_world(bay.center, row.center)
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
                    rack_code=rack_code,
                )

    if not result.targets:
        raise StructureExtractionError(
            "Structure detected but no scan target passed the clearance gate."
        )

    if occupancy_grid is not None:
        _assign_astar_priority(
            result.targets,
            occupancy_grid=occupancy_grid,
            clearance_m=params.required_clearance_m,
        )
    else:
        _assign_serpentine_priority(result.targets)

    result.summary = {
        "frame_id": WAREHOUSE_MAP_FRAME_ID,
        "floor_z": round(floor_z, 3),
        "axis_deg": round(math.degrees(theta), 2),
        "height_band_m": [round(band_lo, 3), round(band_hi, 3)],
        "aisles": aisle_summaries,
        "racks": rack_summaries,
        "counts": {
            "aisles": len(aisle_summaries),
            "racks": len(rack_summaries),
            "targets": len(result.targets),
            "rejected_clearance": result.rejected_clearance,
        },
        "params": _params_to_dict(params),
        "clearance": {
            "source": "point_cloud_kdtree",
            "required_clearance_m": round(params.required_clearance_m, 3),
        },
        "routing": {
            "mode": "occupancy_astar" if occupancy_grid is not None else "aisle_serpentine",
            "source": (
                "persisted_occupancy_grid"
                if occupancy_grid is not None
                else "geometry_ordering"
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


def _detect_shelf_levels(z: np.ndarray, *, spacing: float, res: float) -> list[float]:
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
    candidates = [i for i in range(len(norm)) if norm[i] >= 0.35]
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
    return levels or [0.5 * (z_lo + z_hi)]


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
    rack_code: str,
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

    pitch = max(params.bin_pitch_m, params.grid_res_m * 2)
    n_bins = max(1, round(bay.width / pitch))
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
                    standoff_m=params.standoff_m,
                )
            except ValueError:
                continue

            # Clearance gate: scan pose must be far enough from any structure.
            dist, _ = clearance_tree.query(
                np.array([scan_pose.x_m, scan_pose.y_m, scan_pose.z_m], dtype=np.float64)
            )
            if float(dist) < params.required_clearance_m:
                result.rejected_clearance += 1
                continue

            result.targets.append(
                GeneratedTarget(
                    aisle_code=aisle_code,
                    rack_code=rack_code,
                    shelf_level=level_idx,
                    bin_code=f"B{b_idx + 1}",
                    target_point=target_point.model_dump(),
                    shelf_normal=shelf_normal.model_dump(),
                    scan_pose=scan_pose.model_dump(),
                    standoff_m=float(params.standoff_m),
                    priority=100,
                )
            )


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
        "standoff_m": params.standoff_m,
        "drone_radius_m": params.drone_radius_m,
        "clearance_margin_m": params.clearance_margin_m,
        "axis_deg": params.axis_deg,
    }


def extract_structure_from_flight(
    client_flight_id: str,
    *,
    params: StructureExtractionParams,
) -> StructureResult:
    """Convenience entry point: load the flight cloud then run extraction."""
    params = params.sanitized()
    cloud = load_flight_cloud(client_flight_id, params=params)
    occupancy_grid = load_flight_occupancy_grid(client_flight_id)
    logger.info(
        "structure_extraction loaded flight=%s points=%s voxel=%.3f occupancy=%s",
        client_flight_id,
        cloud.shape[0],
        params.voxel_m,
        occupancy_grid is not None,
    )
    result = extract_structure(cloud, params=params, occupancy_grid=occupancy_grid)
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
