from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
import math

from backend.drone.models import Coordinate
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
    return max(2.0, along), max(2.0, cross)

def build_lawnmower_path(
    polygon_lonlat: List[Tuple[float, float]],
    *,
    altitude_agl: float,
    along_track_m: float,
    cross_track_m: float,
    heading_deg: float = 0.0,
) -> List[Coordinate]:
    """
    Production note:
    - Implement with shapely in service/planning layer for correct clipping.
    - Here: define signature + expected output only.
    """
    # Placeholder: return polygon vertices as a minimal route
    # Replace using backend/services/planning/grid_generator.py
    return [Coordinate(lat=lat, lon=lon, alt=altitude_agl) for lon, lat in polygon_lonlat]

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