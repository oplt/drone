from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Tuple

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
) -> Tuple[float, float]:
    fp_w = _footprint_m(altitude_agl, fov_h)
    fp_h = _footprint_m(altitude_agl, fov_v)
    along = fp_h * (1.0 - front_overlap)
    cross = fp_w * (1.0 - side_overlap)
    return max(0.5, along), max(0.5, cross)


def _interpolate_segment(
    a: Coordinate,
    b: Coordinate,
    *,
    spacing_m: float,
) -> List[Coordinate]:
    dist_m = max(0.0, float(haversine_km(a.lat, a.lon, b.lat, b.lon) * 1000.0))
    if dist_m <= spacing_m:
        return [b]

    steps = max(1, int(math.ceil(dist_m / spacing_m)))
    pts: List[Coordinate] = []
    for i in range(1, steps + 1):
        t = i / steps
        lat = a.lat + (b.lat - a.lat) * t
        lon = a.lon + (b.lon - a.lon) * t
        alt = a.alt + (b.alt - a.alt) * t
        pts.append(Coordinate(lat=lat, lon=lon, alt=alt))
    return pts


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

    for wp in plan.waypoints:
        wp.alt = altitude_agl

    dense: List[Coordinate] = [plan.waypoints[0]]
    for i, b in enumerate(plan.waypoints[1:]):
        a = plan.waypoints[i]
        is_work_leg = bool(plan.work_leg_mask[i]) if i < len(plan.work_leg_mask) else True
        if is_work_leg:
            dense.extend(_interpolate_segment(a, b, spacing_m=along_track_m))
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
) -> PhotogrammetryPlan:
    along, cross = compute_spacings(
        altitude_agl=altitude_agl,
        fov_h=fov_h,
        fov_v=fov_v,
        front_overlap=front_overlap,
        side_overlap=side_overlap,
    )
    wps = build_lawnmower_path(
        polygon_lonlat,
        altitude_agl=altitude_agl,
        along_track_m=along,
        cross_track_m=cross,
        heading_deg=heading_deg,
    )
    return PhotogrammetryPlan(waypoints=wps, along_track_m=along, cross_track_m=cross)
