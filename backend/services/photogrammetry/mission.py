from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterator, List, Tuple

from backend.drone.models import Coordinate
from backend.flight.missions.grid_mission import GridPlanner
from backend.utils.geo import haversine_km


@dataclass(frozen=True)
class PhotogrammetryPlan:
    waypoints: List[Coordinate]
    along_track_m: float
    cross_track_m: float


def _footprint_m(agl_m: float, fov_deg: float) -> float:
    return 2.0 * agl_m * math.tan(math.radians(fov_deg / 2.0))


def compute_spacings(
    *,
    altitude_agl: float,
    fov_h: float,
    fov_v: float,
    front_overlap: float,
    side_overlap: float,
    min_spacing_m: float = 0.5,
) -> Tuple[float, float]:
    fp_w = _footprint_m(altitude_agl, fov_h)
    fp_h = _footprint_m(altitude_agl, fov_v)
    along = fp_h * (1.0 - front_overlap)
    cross = fp_w * (1.0 - side_overlap)
    spacing_floor = max(0.0, float(min_spacing_m))
    return max(spacing_floor, along), max(spacing_floor, cross)


def _segment_distance_m(a: Coordinate, b: Coordinate) -> float:
    return max(0.0, float(haversine_km(a.lat, a.lon, b.lat, b.lon) * 1000.0))


def _interpolate_segment(
    a: Coordinate,
    b: Coordinate,
    *,
    spacing_m: float,
    dist_m: float | None = None,
) -> Iterator[Coordinate]:
    if dist_m is None:
        dist_m = _segment_distance_m(a, b)

    if dist_m <= spacing_m:
        yield b
        return

    steps = max(1, int(math.ceil(dist_m / spacing_m)))
    lat_step = (b.lat - a.lat) / steps
    lon_step = (b.lon - a.lon) / steps
    alt_step = (b.alt - a.alt) / steps
    for i in range(1, steps + 1):
        yield Coordinate(
            lat=a.lat + lat_step * i,
            lon=a.lon + lon_step * i,
            alt=a.alt + alt_step * i,
        )


def build_lawnmower_path(
    polygon_lonlat: List[Tuple[float, float]],
    *,
    altitude_agl: float,
    along_track_m: float,
    cross_track_m: float,
    heading_deg: float = 0.0,
) -> List[Coordinate]:
    """
    Build a clipped lawnmower route and densify work legs to along-track spacing.
    """
    plan = GridPlanner.generate(
        poly_lonlat=polygon_lonlat,
        spacing_m=cross_track_m,
        angle_deg=heading_deg % 180.0,
        inset_m=1.5,
        start_corner="auto",
        lane_strategy="serpentine",
        row_stride=1,
        row_phase_m=0.0,
    )
    if not plan.waypoints:
        return []

    waypoints = plan.waypoints
    work_leg_mask = plan.work_leg_mask

    for wp in waypoints:
        wp.alt = altitude_agl

    dense: List[Coordinate] = [waypoints[0]]
    for i, (a, b) in enumerate(zip(waypoints, waypoints[1:])):
        is_work_leg = bool(work_leg_mask[i]) if i < len(work_leg_mask) else True
        if is_work_leg:
            segment_dist_m = _segment_distance_m(a, b)
            if segment_dist_m <= along_track_m:
                dense.append(b)
                continue
            dense.extend(
                _interpolate_segment(
                    a,
                    b,
                    spacing_m=along_track_m,
                    dist_m=segment_dist_m,
                )
            )
        else:
            dense.append(b)
    return dense


def make_photogrammetry_plan(
    *,
    polygon_lonlat: List[Tuple[float, float]],
    altitude_agl: float,
    fov_h: float,
    fov_v: float,
    front_overlap: float,
    side_overlap: float,
    heading_deg: float = 0.0,
    min_spacing_m: float = 0.5,
) -> PhotogrammetryPlan:
    along, cross = compute_spacings(
        altitude_agl=altitude_agl,
        fov_h=fov_h,
        fov_v=fov_v,
        front_overlap=front_overlap,
        side_overlap=side_overlap,
        min_spacing_m=min_spacing_m,
    )
    wps = build_lawnmower_path(
        polygon_lonlat,
        altitude_agl=altitude_agl,
        along_track_m=along,
        cross_track_m=cross,
        heading_deg=heading_deg,
    )
    return PhotogrammetryPlan(waypoints=wps, along_track_m=along, cross_track_m=cross)
