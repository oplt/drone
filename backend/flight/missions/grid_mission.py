# backend/flight/missions/grid_mission.py
"""
GridMission: field-polygon → lawnmower grid → drone flight.

Architecture
------------
GridPlanner  – pure geometry: polygon → ordered waypoints (no I/O)
GridMission  – frozen dataclass mission that calls GridPlanner at fly-time,
               then delegates to the shared BaseMission execute() path.

Bug fixes applied
-----------------
1. Module-level geo helpers were accidentally nested *inside* the
   ElevationProvider Protocol class body — moved to module scope.
2. GridMission class was missing entirely; its fields + methods were
   floating at the end of GridPlanner.generate() (indentation error).
3. Missing imports: Coordinate, dataclass field(), logging, AgricultureMode.
4. GridPlanResult.waypoints referenced Coordinate before import.
5. _maybe_get_elevation_provider was nested inside ElevationProvider.
6. object.__setattr__ used on a non-frozen dataclass (was inconsistent);
   GridMission is now explicitly frozen=True and documented accordingly.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional, Protocol, Tuple

from shapely.geometry import LineString, Point, Polygon

from backend.db.models import FlightStatus
from backend.drone.models import Coordinate
from backend.flight.missions.terrain_follow import (
    apply_terrain_follow_to_path,
    resolve_home_amsl_m,
)
from backend.utils.geo import coord_from_home

if TYPE_CHECKING:
    from backend.drone.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

AgricultureMode = Literal["mapping", "spray", "ndvi", "multispectral"]
MAX_GRID_ROWS = 1_000
MAX_GRID_WAYPOINTS = 2_200
MAX_GRID_ROUTE_M = 120_000.0
MAX_GRID_PATH_POINTS = 4_000

# ---------------------------------------------------------------------------
# Module-level geo helpers (equirectangular projection, small-area accurate)
# ---------------------------------------------------------------------------

def _meters_per_deg_lat() -> float:
    """Mean metres per degree of latitude (WGS-84 approximation)."""
    return 111_132.0


def _meters_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def _lonlat_to_xy_m(
        lon: float, lat: float, lon0: float, lat0: float
) -> Tuple[float, float]:
    """Equirectangular projection centred at (lon0, lat0) → metres."""
    x = (lon - lon0) * _meters_per_deg_lon(lat0)
    y = (lat - lat0) * _meters_per_deg_lat()
    return x, y


def _xy_m_to_lonlat(
        x: float, y: float, lon0: float, lat0: float
) -> Tuple[float, float]:
    lon = lon0 + x / _meters_per_deg_lon(lat0)
    lat = lat0 + y / _meters_per_deg_lat()
    return lon, lat


def _rot(x: float, y: float, ang_rad: float) -> Tuple[float, float]:
    c, s = math.cos(ang_rad), math.sin(ang_rad)
    return (c * x - s * y, s * x + c * y)


def _poly_centroid_lonlat(
        poly_lonlat: list[Tuple[float, float]],
) -> Tuple[float, float]:
    """Simple mean centroid of an open or closed (lon, lat) ring."""
    if len(poly_lonlat) < 3:
        raise ValueError("Polygon must have ≥ 3 points")
    pts = poly_lonlat[:]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    # Use pts[:-1] so the closing duplicate is excluded from the mean.
    n = len(pts) - 1
    lon0 = sum(p[0] for p in pts[:n]) / n
    lat0 = sum(p[1] for p in pts[:n]) / n
    return lon0, lat0


def _maybe_get_elevation_provider(
        orch: "Orchestrator",
) -> Optional["ElevationProvider"]:
    """Best-effort elevation provider from the orchestrator's maps client.

    Tries the most common attribute names; wraps the callable so callers
    always use ``fn(lat, lon)`` positional form.
    """
    maps = getattr(orch, "maps", None)
    if maps is None:
        return None

    for attr in ("elevation_m", "elevation_at", "get_elevation", "elevation"):
        fn = getattr(maps, attr, None)
        if not callable(fn):
            continue

        def _prov(lat: float, lon: float, _fn=fn) -> float:
            try:
                return float(_fn(lat, lon))
            except TypeError:
                try:
                    return float(_fn(lat=lat, lon=lon))
                except TypeError:
                    return float(_fn((lat, lon)))

        return _prov

    return None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class ElevationProvider(Protocol):
    """Callable: (lat, lon) → metres above MSL."""

    def __call__(self, lat: float, lon: float) -> float: ...


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridPlanResult:
    waypoints: list[Coordinate]
    work_leg_mask: list[bool]   # len == len(waypoints) - 1
    angle_deg: float
    spacing_m: float
    stats: dict


def _coords_close(a: Coordinate, b: Coordinate, tol: float = 1e-7) -> bool:
    return abs(a.lat - b.lat) <= tol and abs(a.lon - b.lon) <= tol


def _route_length_m(
        waypoints: list[Coordinate],
        lon0: float,
        lat0: float,
) -> float:
    if len(waypoints) < 2:
        return 0.0
    xy = [_lonlat_to_xy_m(w.lon, w.lat, lon0, lat0) for w in waypoints]
    return float(
        sum(
            math.hypot(x2 - x1, y2 - y1)
            for (x1, y1), (x2, y2) in zip(xy, xy[1:])
        )
    )


def _validate_plan_limits(plan: GridPlanResult) -> None:
    rows = int(plan.stats.get("rows", 0))
    waypoints = len(plan.waypoints)
    route_m = float(plan.stats.get("route_m", 0.0) or 0.0)

    if rows > MAX_GRID_ROWS:
        raise ValueError(
            f"Grid has {rows} rows, exceeding the limit of {MAX_GRID_ROWS}. "
            "Increase row spacing, increase row stride, or split the field."
        )
    if waypoints > MAX_GRID_WAYPOINTS:
        raise ValueError(
            f"Grid has {waypoints} waypoints, exceeding the limit of {MAX_GRID_WAYPOINTS}. "
            "Increase row spacing, increase row stride, or split the field."
        )
    if route_m > MAX_GRID_ROUTE_M:
        raise ValueError(
            f"Grid route is {route_m:.1f} m, exceeding the limit of {MAX_GRID_ROUTE_M:.0f} m. "
            "Increase spacing/stride or divide the survey into multiple missions."
        )


def combine_grid_plans(
        plans: list[GridPlanResult],
        poly_lonlat: list[Tuple[float, float]],
        pattern_mode: str,
) -> GridPlanResult:
    """Concatenate one or more grid plans into a single flyable route."""
    if not plans:
        raise ValueError("No grid plans to combine")

    combined_waypoints = list(plans[0].waypoints)
    combined_mask = list(plans[0].work_leg_mask)

    for plan in plans[1:]:
        if not plan.waypoints:
            continue

        first = plan.waypoints[0]
        if not combined_waypoints:
            combined_waypoints = list(plan.waypoints)
            combined_mask = list(plan.work_leg_mask)
            continue

        if not _coords_close(combined_waypoints[-1], first):
            combined_waypoints.append(first)
            combined_mask.append(False)  # transit connector between passes

        combined_waypoints.extend(plan.waypoints[1:])
        combined_mask.extend(plan.work_leg_mask)

    lon0, lat0 = _poly_centroid_lonlat(poly_lonlat)
    route_m = round(_route_length_m(combined_waypoints, lon0, lat0), 1)

    area_m2 = float(plans[0].stats.get("area_m2", 0.0))
    rows = sum(int(p.stats.get("rows", 0)) for p in plans)
    return GridPlanResult(
        waypoints=combined_waypoints,
        work_leg_mask=combined_mask,
        angle_deg=float(plans[0].angle_deg),
        spacing_m=float(plans[0].spacing_m),
        stats={
            "pattern_mode": pattern_mode,
            "passes": len(plans),
            "angles_deg": [round(float(p.angle_deg), 3) for p in plans],
            "rows": rows,
            "waypoints": len(combined_waypoints),
            "route_m": route_m,
            "area_m2": round(area_m2, 1),
        },
    )


# ---------------------------------------------------------------------------
# GridPlanner – pure geometry, no I/O
# ---------------------------------------------------------------------------

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
            poly_lonlat: list[Tuple[float, float]],
    ) -> list[Tuple[float, float]]:
        if len(poly_lonlat) < 3:
            raise ValueError("Polygon must have ≥ 3 points")
        if poly_lonlat[0] != poly_lonlat[-1]:
            return poly_lonlat + [poly_lonlat[0]]
        return poly_lonlat

    @staticmethod
    def _poly_xy(
            poly_lonlat: list[Tuple[float, float]], lon0: float, lat0: float
    ) -> Polygon:
        pts = GridPlanner._ensure_closed(poly_lonlat)
        pts_xy = [_lonlat_to_xy_m(lon, lat, lon0, lat0) for lon, lat in pts]
        poly = Polygon(pts_xy)
        if not poly.is_valid or poly.area <= 0:
            raise ValueError("Invalid polygon (self-intersection or zero area)")
        return poly

    @staticmethod
    def _sample_points_in_poly(
            poly: Polygon, n: int
    ) -> list[Tuple[float, float]]:
        minx, miny, maxx, maxy = poly.bounds
        pts: list[Tuple[float, float]] = []
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
            poly_lonlat: list[Tuple[float, float]],
            elev: ElevationProvider,
            sample_n: int = 120,
            delta_m: float = 8.0,
    ) -> Tuple[float, float]:
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
    def slope_aware_angle_deg(
            poly_lonlat: list[Tuple[float, float]],
            elev: ElevationProvider,
    ) -> float:
        """Pick grid orientation aligned with terrain contours.

        Row direction u = rot90(∇z) = (−dz/dy, dz/dx) minimises
        altitude change along each work leg.
        """
        gx, gy = GridPlanner.estimate_mean_gradient(poly_lonlat, elev)
        if abs(gx) < 1e-6 and abs(gy) < 1e-6:
            return 0.0
        ux, uy = -gy, gx
        return math.degrees(math.atan2(uy, ux)) % 180.0

    @staticmethod
    def slope_corrected_spacing_m(
            base_spacing_m: float,
            angle_deg: float,
            mean_gradient: Tuple[float, float],
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
            poly_lonlat: list[Tuple[float, float]],
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

        def to_rot(x: float, y: float) -> Tuple[float, float]:
            return _rot(x, y, -ang)

        def from_rot(xr: float, yr: float) -> Tuple[float, float]:
            return _rot(xr, yr, ang)

        poly_rot = Polygon([to_rot(x, y) for x, y in poly.exterior.coords])
        minx, miny, maxx, maxy = poly_rot.bounds

        # Sweep vertical scan-lines across the rotated polygon.
        phase_m = float(row_phase_m) % float(spacing_m)
        x = minx - spacing_m + phase_m
        segments: list[Tuple[float, LineString]] = []
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
            raise ValueError(
                "No grid segments generated — check spacing/inset vs field size"
            )

        segments.sort(key=lambda t: t[0])
        if row_stride > 1:
            segments = [seg for i, seg in enumerate(segments) if i % row_stride == 0]
            if not segments:
                raise ValueError("No rows left after applying row_stride")

        if start_corner in ("ne", "se"):
            segments = list(reversed(segments))

        waypoints_lonlat: list[Tuple[float, float]] = []
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
                work_mask.append(False)     # connector / turn
                waypoints_lonlat.append((blon, blat))
                work_mask.append(True)      # imaging / spray leg

        wps = [Coordinate(lat=lat, lon=lon) for lon, lat in waypoints_lonlat]

        # Compute total route length in metres.
        xy = [_lonlat_to_xy_m(w.lon, w.lat, lon0, lat0) for w in wps]
        dist_m = sum(
            math.hypot(x2 - x1, y2 - y1)
            for (x1, y1), (x2, y2) in zip(xy, xy[1:])
        )

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
            },
        )


# ---------------------------------------------------------------------------
# GridMission – frozen dataclass, compatible with BaseMission execute() path
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridMission:
    """Agricultural lawnmower mission over a field polygon.

    Usage A – pre-computed waypoints
    ---------------------------------
    Provide ``waypoints`` (≥ 2 Coordinates); planning is skipped.

    Usage B – polygon-driven planning (preferred for agri tasks)
    -------------------------------------------------------------
    Provide ``field_polygon_lonlat`` and leave ``waypoints`` empty.
    The planner runs inside ``fly_grid()`` so elevation data is available.

    The class is **frozen** (immutable after construction) for safety.
    Internal state mutations during planning use ``object.__setattr__``,
    which is the standard pattern for frozen dataclasses.
    """

    # --- Required / core ---
    cruise_alt_m: float = 30.0

    # --- Mission mode ---
    mode: AgricultureMode = "mapping"

    # --- Waypoints (pre-computed or filled by planner) ---
    waypoints: list[Coordinate] = field(default_factory=list)
    work_leg_mask: list[bool] = field(default_factory=list)

    # --- Polygon-driven planning ---
    field_polygon_lonlat: Optional[list[Tuple[float, float]]] = None  # [(lon, lat), …]
    row_spacing_m: float = 7.5
    grid_angle_deg: Optional[float] = None  # None + slope_aware → contour-aligned
    slope_aware: bool = False
    safety_inset_m: float = 1.5

    # --- Terrain following ---
    terrain_follow: bool = False
    agl_m: float = 30.0  # above-ground-level; used only when terrain_follow=True
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    crosshatch_angle_offset_deg: float = 90.0
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    row_stride: int = 1
    row_phase_m: float = 0.0
    interpolate_steps: int = 6

    # ------------------------------------------------------------------
    # BaseMission interface
    # ------------------------------------------------------------------

    def get_waypoints(self) -> list[Coordinate]:
        """Called by orchestrator for pre-flight distance estimation."""
        if len(self.waypoints) >= 2:
            return list(self.waypoints)

        if not self.field_polygon_lonlat:
            raise ValueError(
                "GridMission requires at least 2 waypoints OR field_polygon_lonlat."
            )

        # Return a placeholder (centroid → centroid) so the orchestrator can
        # proceed; real waypoints are computed lazily inside fly_grid().
        lon0, lat0 = _poly_centroid_lonlat(self.field_polygon_lonlat)
        c = Coordinate(lat=lat0, lon=lon0, alt=self.cruise_alt_m)
        return [c, c]

    async def execute(self, orch: "Orchestrator", *, alt: float = 30.0) -> None:
        """Entry point called by the generic execute_mission runner."""
        # Allow caller-supplied alt to override cruise_alt_m.
        if alt != self.cruise_alt_m:
            object.__setattr__(self, "cruise_alt_m", alt)
        effective_alt = float(self.agl_m if self.terrain_follow else self.cruise_alt_m)
        await orch.run_mission(
            self,
            alt=effective_alt,
            flight_fn=lambda: self.fly_grid(orch),
        )

    # ------------------------------------------------------------------
    # Planning + execution
    # ------------------------------------------------------------------

    async def fly_grid(self, orch: "Orchestrator") -> None:
        """Plan (if needed) and fly the lawnmower route."""
        if len(self.waypoints) < 2:
            if not self.field_polygon_lonlat:
                raise ValueError(
                    "GridMission needs ≥ 2 waypoints or field_polygon_lonlat."
                )
            await self._plan_grid(orch)

        anchors = self._build_route(orch, cruise_alt=self.cruise_alt_m)
        await self._stitch_path(orch, anchors)

    async def _plan_grid(self, orch: "Orchestrator") -> None:
        """Run GridPlanner and (optionally) apply terrain following."""
        elev = _maybe_get_elevation_provider(orch)
        angle: Optional[float] = self.grid_angle_deg
        spacing = float(self.row_spacing_m)

        if self.slope_aware:
            if elev is None:
                logger.warning(
                    "GridMission: slope_aware=True but no elevation provider found; "
                    "falling back to angle=0°"
                )
                angle = angle if angle is not None else 0.0
            else:
                if angle is None:
                    angle = GridPlanner.slope_aware_angle_deg(
                        self.field_polygon_lonlat, elev
                    )
                gxgy = GridPlanner.estimate_mean_gradient(
                    self.field_polygon_lonlat, elev
                )
                spacing = GridPlanner.slope_corrected_spacing_m(
                    spacing, float(angle), gxgy
                )

        if angle is None:
            angle = 0.0

        primary = GridPlanner.generate(
            self.field_polygon_lonlat,
            spacing_m=float(spacing),
            angle_deg=float(angle),
            inset_m=float(self.safety_inset_m),
            start_corner=self.start_corner,
            lane_strategy=self.lane_strategy,
            row_stride=max(1, int(self.row_stride)),
            row_phase_m=float(self.row_phase_m),
        )
        plans = [primary]

        if self.pattern_mode == "crosshatch":
            angle2 = (float(angle) + float(self.crosshatch_angle_offset_deg)) % 180.0
            if not math.isclose(angle2, float(angle), abs_tol=1e-6):
                secondary = GridPlanner.generate(
                    self.field_polygon_lonlat,
                    spacing_m=float(spacing),
                    angle_deg=float(angle2),
                    inset_m=float(self.safety_inset_m),
                    start_corner=self.start_corner,
                    lane_strategy=self.lane_strategy,
                    row_stride=max(1, int(self.row_stride)),
                    row_phase_m=float(self.row_phase_m),
                )
                plans.append(secondary)

        plan = combine_grid_plans(
            plans=plans,
            poly_lonlat=self.field_polygon_lonlat,
            pattern_mode=self.pattern_mode,
        )
        _validate_plan_limits(plan)

        object.__setattr__(self, "waypoints", plan.waypoints)
        object.__setattr__(self, "work_leg_mask", plan.work_leg_mask)

        # Log the plan to the flight event repo.
        await self._add_event_safe(
            orch,
            "grid_planned",
            {"angle_deg": plan.angle_deg, "spacing_m": plan.spacing_m, **plan.stats},
        )
        logger.info(
            "Grid planned: mode=%s rows=%d waypoints=%d route=%.0f m",
            self.pattern_mode,
            plan.stats["rows"],
            plan.stats["waypoints"],
            plan.stats["route_m"],
        )

        # Terrain following is applied after interpolation in _stitch_path()
        # so altitude remains terrain-aware across the full flown path.

    # ------------------------------------------------------------------
    # Stubs - these are provided by BaseMission in the real codebase.
    # Defined here so the file is self-consistent for type checking.
    # ------------------------------------------------------------------

    async def _add_event_safe(
            self,
            orch: "Orchestrator",
            event_type: str,
            data: Optional[dict] = None,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            logger.warning(
                "GridMission: skipping event '%s' because flight_id is unavailable",
                event_type,
            )
            return
        try:
            await orch.repo.add_event(flight_id, event_type, data or {})
        except Exception:
            logger.exception(
                "GridMission: failed to persist event '%s' (flight_id=%s)",
                event_type,
                flight_id,
            )

    def _build_route(self, orch: "Orchestrator", *, cruise_alt: float) -> list:
        if len(self.waypoints) < 2:
            raise ValueError("GridMission requires at least 2 planned waypoints.")

        home = coord_from_home(orch.drone.home_location)
        home.alt = float(self.agl_m if self.terrain_follow else cruise_alt)

        route = [home]
        for wp in self.waypoints:
            alt = wp.alt if getattr(wp, "alt", None) is not None else cruise_alt
            route.append(Coordinate(lat=wp.lat, lon=wp.lon, alt=float(alt)))
        route.append(home)

        orch._dest_coord = route[-2]
        return route

    async def _stitch_path(self, orch: "Orchestrator", anchors: list) -> None:
        if len(anchors) < 2:
            raise ValueError("Grid route requires at least 2 anchors.")

        takeoff_alt_m = float(self.agl_m if self.terrain_follow else self.cruise_alt_m)
        await asyncio.sleep(1.0)
        await asyncio.to_thread(orch.drone.arm_and_takeoff, takeoff_alt_m)

        await self._add_event_safe(orch, "takeoff", {})

        requested_steps = max(0, int(self.interpolate_steps))
        segment_count = max(1, len(anchors) - 1)
        max_steps_by_budget = max(0, (MAX_GRID_PATH_POINTS // segment_count) - 1)
        interpolate_steps = min(requested_steps, max_steps_by_budget)
        if interpolate_steps < requested_steps:
            logger.info(
                "GridMission: interpolation reduced from %d to %d for %d segments",
                requested_steps,
                interpolate_steps,
                segment_count,
            )
        path: list[Coordinate] = []
        for a, b in zip(anchors, anchors[1:]):
            seg = (
                list(orch.maps.waypoints_between(a, b, steps=interpolate_steps))
                if interpolate_steps > 0
                else [a, b]
            )
            if path and seg:
                prev = path[-1]
                first = seg[0]
                if (
                    abs(prev.lat - first.lat) <= 1e-9
                    and abs(prev.lon - first.lon) <= 1e-9
                    and abs(float(prev.alt) - float(first.alt)) <= 1e-6
                ):
                    seg = seg[1:]
            path.extend(seg)

        if not path:
            raise ValueError("GridMission produced an empty route path")

        if self.terrain_follow:
            home_amsl_m = await asyncio.to_thread(resolve_home_amsl_m, orch.drone)
            path = await apply_terrain_follow_to_path(
                maps_client=orch.maps,
                path=path,
                home_amsl_m=home_amsl_m,
                target_agl_m=float(self.agl_m),
            )
            await self._add_event_safe(
                orch,
                "grid_terrain_follow_applied",
                {
                    "path_points": len(path),
                    "target_agl_m": float(self.agl_m),
                    "takeoff_alt_m": takeoff_alt_m,
                },
            )

        await asyncio.to_thread(orch.drone.follow_waypoints, path)

        await self._add_event_safe(orch, "reached_destination", {})

        await asyncio.to_thread(orch.drone.land)
        await self._add_event_safe(orch, "landing_command_sent", {})

        await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)

        await self._add_event_safe(orch, "landed_home", {})
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is not None:
            try:
                await orch.repo.finish_flight(
                    flight_id,
                    status=FlightStatus.COMPLETED,
                    note="Grid mission completed and returned home",
                )
            except Exception:
                logger.exception(
                    "GridMission: failed to finish flight in repository (flight_id=%s)",
                    flight_id,
                )
