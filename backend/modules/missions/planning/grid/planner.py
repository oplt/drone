from __future__ import annotations

import math
import random
from typing import Literal

from shapely.geometry import LineString, Point, Polygon

from backend.core.geometry.algorithm_runtime import (
    GEOMETRY_ALGORITHM_VERSION,
    geometry_plan_cache,
    workload_label,
)
from backend.core.geometry.projection import (
    lonlat_to_xy_m as _lonlat_to_xy_m,
)
from backend.core.geometry.projection import (
    xy_m_to_lonlat as _xy_m_to_lonlat,
)
from backend.modules.missions.planning.grid.constants import (
    MAX_GRID_PATH_POINTS,
    MAX_GRID_ROWS,
    MAX_GRID_ROUTE_M,
    MAX_GRID_WAYPOINTS,
)
from backend.modules.missions.planning.grid.elevation import (
    BatchElevationProvider,
    ElevationProvider,
)
from backend.modules.missions.planning.grid.geo import (
    _poly_centroid_lonlat,
    _rot,
)
from backend.modules.missions.planning.grid.models import GridPlanResult
from backend.modules.vehicle_runtime.types import Coordinate


class GridPlanner:
    """Field polygon → clipped lawnmower grid → ordered route.

    All geometry is done in a local tangent plane (metres) then converted
    back to lon/lat.
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_closed(
        poly_lonlat: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        if len(poly_lonlat) < 3:
            raise ValueError("Polygon must have ≥ 3 points")
        if poly_lonlat[0] != poly_lonlat[-1]:
            return poly_lonlat + [poly_lonlat[0]]
        return poly_lonlat

    @staticmethod
    def _poly_xy(poly_lonlat: list[tuple[float, float]], lon0: float, lat0: float) -> Polygon:
        pts = GridPlanner._ensure_closed(poly_lonlat)
        pts_xy = [_lonlat_to_xy_m(lon, lat, lon0, lat0) for lon, lat in pts]
        poly = Polygon(pts_xy)
        if not poly.is_valid or poly.area <= 0:
            raise ValueError("Invalid polygon (self-intersection or zero area)")
        return poly

    @staticmethod
    def _sample_points_in_poly(poly: Polygon, n: int) -> list[tuple[float, float]]:
        minx, miny, maxx, maxy = poly.bounds
        pts: list[tuple[float, float]] = []
        tries = 0
        while len(pts) < n and tries < n * 80:
            tries += 1
            x = random.uniform(minx, maxx)
            y = random.uniform(miny, maxy)
            if poly.contains(Point(x, y)):
                pts.append((x, y))
        return pts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_mean_gradient(
        poly_lonlat: list[tuple[float, float]],
        elev: ElevationProvider,
        sample_n: int = 120,
        delta_m: float = 8.0,
    ) -> tuple[float, float]:
        """Estimate mean terrain gradient (dz/dx, dz/dy) over the polygon.

        Uses central finite differences at random interior points:
          dz/dx ≈ (z(x+δ, y) − z(x−δ, y)) / 2δ
          dz/dy ≈ (z(x, y+δ) − z(x, y−δ)) / 2δ
        """
        lon0, lat0 = _poly_centroid_lonlat(poly_lonlat)
        poly = GridPlanner._poly_xy(poly_lonlat, lon0, lat0)

        pts = GridPlanner._sample_points_in_poly(poly, sample_n)
        if not pts:
            return 0.0, 0.0

        gxs: list[float] = []
        gys: list[float] = []
        for x, y in pts:
            lon_p, lat_p = _xy_m_to_lonlat(x + delta_m, y, lon0, lat0)
            lon_m, lat_m = _xy_m_to_lonlat(x - delta_m, y, lon0, lat0)
            dzdx = (elev(lat_p, lon_p) - elev(lat_m, lon_m)) / (2.0 * delta_m)

            lon_p, lat_p = _xy_m_to_lonlat(x, y + delta_m, lon0, lat0)
            lon_m, lat_m = _xy_m_to_lonlat(x, y - delta_m, lon0, lat0)
            dzdy = (elev(lat_p, lon_p) - elev(lat_m, lon_m)) / (2.0 * delta_m)

            if math.isfinite(dzdx) and math.isfinite(dzdy):
                gxs.append(dzdx)
                gys.append(dzdy)

        if not gxs:
            return 0.0, 0.0
        return sum(gxs) / len(gxs), sum(gys) / len(gys)

    @staticmethod
    def estimate_mean_gradient_batched(
        poly_lonlat: list[tuple[float, float]],
        elev_many: BatchElevationProvider,
        sample_n: int = 120,
        delta_m: float = 8.0,
    ) -> tuple[float, float]:
        """Estimate mean terrain gradient using batched elevation lookups."""
        lon0, lat0 = _poly_centroid_lonlat(poly_lonlat)
        poly = GridPlanner._poly_xy(poly_lonlat, lon0, lat0)

        pts = GridPlanner._sample_points_in_poly(poly, sample_n)
        if not pts:
            return 0.0, 0.0

        sample_indexes: list[tuple[int, int, int, int]] = []
        coords: list[tuple[float, float]] = []
        for x, y in pts:
            lon_p, lat_p = _xy_m_to_lonlat(x + delta_m, y, lon0, lat0)
            lon_m, lat_m = _xy_m_to_lonlat(x - delta_m, y, lon0, lat0)
            x_plus_idx = len(coords)
            coords.append((lat_p, lon_p))
            x_minus_idx = len(coords)
            coords.append((lat_m, lon_m))

            lon_p, lat_p = _xy_m_to_lonlat(x, y + delta_m, lon0, lat0)
            lon_m, lat_m = _xy_m_to_lonlat(x, y - delta_m, lon0, lat0)
            y_plus_idx = len(coords)
            coords.append((lat_p, lon_p))
            y_minus_idx = len(coords)
            coords.append((lat_m, lon_m))
            sample_indexes.append((x_plus_idx, x_minus_idx, y_plus_idx, y_minus_idx))

        values = elev_many(coords)
        if len(values) != len(coords):
            raise ValueError(
                f"Batched gradient lookup returned {len(values)} values for {len(coords)} coordinates."
            )

        gxs: list[float] = []
        gys: list[float] = []
        for x_plus_idx, x_minus_idx, y_plus_idx, y_minus_idx in sample_indexes:
            dzdx = (values[x_plus_idx] - values[x_minus_idx]) / (2.0 * delta_m)
            dzdy = (values[y_plus_idx] - values[y_minus_idx]) / (2.0 * delta_m)

            if math.isfinite(dzdx) and math.isfinite(dzdy):
                gxs.append(dzdx)
                gys.append(dzdy)

        if not gxs:
            return 0.0, 0.0
        return sum(gxs) / len(gxs), sum(gys) / len(gys)

    @staticmethod
    def contour_aligned_angle_deg(mean_gradient: tuple[float, float]) -> float:
        gx, gy = mean_gradient
        if abs(gx) < 1e-6 and abs(gy) < 1e-6:
            return 0.0
        ux, uy = -gy, gx
        return math.degrees(math.atan2(uy, ux)) % 180.0

    @staticmethod
    def slope_aware_angle_deg(
        poly_lonlat: list[tuple[float, float]],
        elev: ElevationProvider,
    ) -> float:
        """Pick grid orientation aligned with terrain contours.

        Row direction u = rot90(∇z) = (−dz/dy, dz/dx) minimises
        altitude change along each work leg.
        """
        gxgy = GridPlanner.estimate_mean_gradient(poly_lonlat, elev)
        return GridPlanner.contour_aligned_angle_deg(gxgy)

    @staticmethod
    def slope_corrected_spacing_m(
        base_spacing_m: float,
        angle_deg: float,
        mean_gradient: tuple[float, float],
    ) -> float:
        """Shrink horizontal spacing so *ground* spacing stays ≈ constant on slopes.

        Along cross-track direction v:
          ds_ground = ds_horiz × √(1 + (∇z·v)²)
          → ds_horiz = base / √(1 + (∇z·v)²)
        """
        if base_spacing_m <= 0:
            raise ValueError("base_spacing_m must be > 0")
        gx, gy = mean_gradient
        ang = math.radians(angle_deg)
        vx, vy = -math.sin(ang), math.cos(ang)
        dzds = gx * vx + gy * vy
        return float(base_spacing_m / math.sqrt(1.0 + dzds * dzds))

    @staticmethod
    def generate(
        poly_lonlat: list[tuple[float, float]],
        spacing_m: float,
        angle_deg: float,
        *,
        inset_m: float = 1.5,
        min_segment_m: float = 3.0,
        start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto",
        lane_strategy: Literal["serpentine", "one_way"] = "serpentine",
        row_stride: int = 1,
        row_phase_m: float = 0.0,
    ) -> GridPlanResult:
        payload = {
            "polygon": [[float(lon), float(lat)] for lon, lat in poly_lonlat],
            "spacing_m": float(spacing_m),
            "angle_deg": float(angle_deg),
            "inset_m": float(inset_m),
            "min_segment_m": float(min_segment_m),
            "start_corner": start_corner,
            "lane_strategy": lane_strategy,
            "row_stride": int(row_stride),
            "row_phase_m": float(row_phase_m),
        }
        return geometry_plan_cache.get_or_compute(
            namespace="grid_plan",
            algorithm_version=GEOMETRY_ALGORITHM_VERSION,
            payload=payload,
            workload=workload_label(vertices=len(poly_lonlat)),
            compute=lambda: GridPlanner._generate_uncached(
                poly_lonlat,
                spacing_m,
                angle_deg,
                inset_m=inset_m,
                min_segment_m=min_segment_m,
                start_corner=start_corner,
                lane_strategy=lane_strategy,
                row_stride=row_stride,
                row_phase_m=row_phase_m,
            ),
        )

    @staticmethod
    def _generate_uncached(
        poly_lonlat: list[tuple[float, float]],
        spacing_m: float,
        angle_deg: float,
        *,
        inset_m: float = 1.5,
        min_segment_m: float = 3.0,
        start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto",
        lane_strategy: Literal["serpentine", "one_way"] = "serpentine",
        row_stride: int = 1,
        row_phase_m: float = 0.0,
    ) -> GridPlanResult:
        """Generate a clipped lawnmower route inside *poly_lonlat*.

        Returns
        -------
        GridPlanResult
            waypoints     – ordered Coordinate list (ready for the drone)
            work_leg_mask – True on spray/imaging legs, False on turn legs
                            len == len(waypoints) - 1
        """
        if spacing_m <= 0:
            raise ValueError("spacing_m must be > 0")
        if row_stride < 1:
            raise ValueError("row_stride must be >= 1")

        poly_lonlat = GridPlanner._ensure_closed(poly_lonlat)
        lon0, lat0 = _poly_centroid_lonlat(poly_lonlat)
        poly = GridPlanner._poly_xy(poly_lonlat, lon0, lat0)

        if inset_m > 0:
            poly = poly.buffer(-float(inset_m))
            if poly.is_empty or poly.area <= 0:
                raise ValueError("Inset too large: polygon vanished after buffering")

        ang = math.radians(angle_deg)

        def to_rot(x: float, y: float) -> tuple[float, float]:
            return _rot(x, y, -ang)

        def from_rot(xr: float, yr: float) -> tuple[float, float]:
            return _rot(xr, yr, ang)

        poly_rot = Polygon([to_rot(x, y) for x, y in poly.exterior.coords])
        minx, miny, maxx, maxy = poly_rot.bounds

        # Sweep vertical scan-lines across the rotated polygon.
        phase_m = float(row_phase_m) % float(spacing_m)
        x = minx - spacing_m + phase_m
        segments: list[tuple[float, LineString]] = []
        while x <= maxx + spacing_m:
            line = LineString([(x, miny - 10_000.0), (x, maxy + 10_000.0)])
            inter = poly_rot.intersection(line)
            if not inter.is_empty:
                geoms = (
                    [inter]
                    if inter.geom_type == "LineString"
                    else list(inter.geoms)
                    if inter.geom_type == "MultiLineString"
                    else []
                )
                for g in geoms:
                    if g.length >= min_segment_m:
                        segments.append((x, g))
            x += spacing_m

        if not segments:
            raise ValueError("No grid segments generated — check spacing/inset vs field size")

        segments.sort(key=lambda t: t[0])
        if row_stride > 1:
            segments = [seg for i, seg in enumerate(segments) if i % row_stride == 0]
            if not segments:
                raise ValueError("No rows left after applying row_stride")

        if start_corner in ("ne", "se"):
            segments = list(reversed(segments))

        waypoints_lonlat: list[tuple[float, float]] = []
        work_mask: list[bool] = []
        first_top_to_bottom = start_corner in ("nw", "ne")

        for i, (_x, seg) in enumerate(segments):
            coords = list(seg.coords)
            p0, p1 = coords[0], coords[-1]
            lower, upper = (p0, p1) if p0[1] <= p1[1] else (p1, p0)

            top_to_bottom = first_top_to_bottom
            if lane_strategy == "serpentine" and i % 2 == 1:
                top_to_bottom = not top_to_bottom

            a, b = (upper, lower) if top_to_bottom else (lower, upper)

            ax, ay = from_rot(*a)
            bx, by = from_rot(*b)
            alon, alat = _xy_m_to_lonlat(ax, ay, lon0, lat0)
            blon, blat = _xy_m_to_lonlat(bx, by, lon0, lat0)

            if not waypoints_lonlat:
                # First segment: two waypoints, one work-leg mask entry.
                waypoints_lonlat.extend([(alon, alat), (blon, blat)])
                work_mask.append(True)
            else:
                # Turn leg then work leg.
                waypoints_lonlat.append((alon, alat))
                work_mask.append(False)  # connector / turn
                waypoints_lonlat.append((blon, blat))
                work_mask.append(True)  # imaging / spray leg

        wps = [Coordinate(lat=lat, lon=lon) for lon, lat in waypoints_lonlat]

        # Compute total route length in metres.
        xy = [_lonlat_to_xy_m(w.lon, w.lat, lon0, lat0) for w in wps]
        dist_m = sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(xy, xy[1:]))

        return GridPlanResult(
            waypoints=wps,
            work_leg_mask=work_mask,
            angle_deg=float(angle_deg),
            spacing_m=float(spacing_m),
            stats={
                "rows": len(segments),
                "waypoints": len(wps),
                "route_m": round(dist_m, 1),
                "area_m2": round(float(poly.area), 1),
                "start_corner": start_corner,
                "lane_strategy": lane_strategy,
                "row_stride": int(row_stride),
                "row_phase_m": round(phase_m, 3),
                "limits": {
                    "max_rows": MAX_GRID_ROWS,
                    "max_waypoints": MAX_GRID_WAYPOINTS,
                    "max_route_m": MAX_GRID_ROUTE_M,
                    "max_path_points": MAX_GRID_PATH_POINTS,
                    "retry_limit": 0,
                },
            },
        )
