import math
import os
from collections.abc import Iterable, Sequence
from math import atan, pi, radians, tan
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from backend.modules.missions.schemas.mission_types import (
    AdaptiveAltitudeMission,
    GridMission,
    IndoorExplorationMission,
    OrbitMission,
    PerimeterPatrolMission,
    TerrainFollowMission,
    WarehouseScanMission,
    Waypoint,
)
from backend.modules.preflight.range_estimator import SimpleWhPerKmModel
from backend.modules.vehicle_runtime.types import Coordinate

from .context import PreflightContext
from .schemas import CheckResult, CheckStatus


def _warehouse_sim_mode() -> bool:
    enabled_values = {"1", "true", "yes", "on"}
    for name in ("SIM_MODE", "INDOOR_NAV", "WAREHOUSE_SIM_MODE", "WAREHOUSE_GAZEBO_SIM"):
        if os.getenv(name, "").strip().lower() in enabled_values:
            return True
    return False


class MissionPreflightBase:
    """Base class for mission-specific preflight checks."""

    def __init__(self, context: PreflightContext):
        """
        Initialize with context.

        Args:
            context: PreflightContext containing all necessary data
        """
        self.ctx = context
        self.v = context.vehicle_state
        self.mission = context.mission

        # FIX (Bug 4): range_model was never initialised on this base class,
        # causing AttributeError inside check_preflight_range.
        self.range_model = SimpleWhPerKmModel()

        # Default thresholds from context
        self.A_LAT_MAX = context.get_threshold("A_LAT_MAX", 9.81)
        self.BANK_MAX_DEG = context.get_threshold("BANK_MAX_DEG", 35)
        self.TURN_PENALTY_S = context.get_threshold("TURN_PENALTY_S", 5)
        self.AGL_MIN = context.get_threshold("AGL_MIN", 10)
        self.AGL_MAX = context.get_threshold("AGL_MAX", 120)

    def _get_distance(self, idx1: int, idx2: int) -> float:
        """Get cached distance between waypoints."""
        return self.ctx.get_distance(idx1, idx2)

    def _get_terrain(self, idx: int) -> float | None:
        """Get cached terrain elevation."""
        return self.ctx.get_waypoint_terrain(idx)

    def _thr(self, key: str, default: Any) -> Any:
        """Read threshold from context with a default."""
        return self.ctx.get_threshold(key, default)

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine distance in meters."""
        R = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def _as_latlon(self, p: Any) -> tuple[float, float] | None:
        """Best-effort extraction of (lat, lon) from waypoint/polygon point."""
        try:
            if isinstance(p, (tuple, list)) and len(p) >= 2:
                return float(p[0]), float(p[1])
            if isinstance(p, dict) and "lat" in p and "lon" in p:
                return float(p["lat"]), float(p["lon"])
            if hasattr(p, "lat") and hasattr(p, "lon"):
                return float(p.lat), float(p.lon)
            if hasattr(p, "latitude") and hasattr(p, "longitude"):
                return float(p.latitude), float(p.longitude)
        except Exception:
            return None
        return None

    def _normalize_polygon(self, poly: Iterable[Any]) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for p in poly:
            ll = self._as_latlon(p)
            if ll is not None:
                pts.append(ll)
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts.pop()
        return pts

    @staticmethod
    def _point_in_polygon(lat: float, lon: float, polygon: Sequence[tuple[float, float]]) -> bool:
        """Ray casting point-in-polygon (lat/lon treated as local planar coords)."""
        if len(polygon) < 3:
            return False
        x = lon
        y = lat
        inside = False
        n = len(polygon)
        for i in range(n):
            y1, x1 = polygon[i]
            y2, x2 = polygon[(i + 1) % n]
            intersects = ((y1 > y) != (y2 > y)) and (
                x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-16) + x1
            )
            if intersects:
                inside = not inside
        return inside

    def _mission_points(self) -> list[tuple[float, float]]:
        """Representative mission points for containment/range checks."""
        pts: list[tuple[float, float]] = []
        wps = getattr(self.mission, "waypoints", None)
        if wps:
            for wp in wps:
                ll = self._as_latlon(wp)
                if ll:
                    pts.append(ll)
        poly = getattr(self.mission, "polygon", None)
        if poly:
            for p in poly:
                ll = self._as_latlon(p)
                if ll:
                    pts.append(ll)
        return pts

    def _total_route_distance_m(self, home: Coordinate, route: list[Coordinate]) -> float:
        """Total mission distance (km): home→route[0]→...→route[-1]→home."""
        if not route:
            return 0.0
        total = self._haversine_m(home.lat, home.lon, route[0].lat, route[0].lon)
        for a, b in zip(route, route[1:]):
            total += self._haversine_m(a.lat, a.lon, b.lat, b.lon)
        total += self._haversine_m(route[-1].lat, route[-1].lon, home.lat, home.lon)
        return total

    # -------------------------
    # Recommended mission-common checks (still mission-specific)
    # -------------------------

    def check_speed_limits(self) -> CheckResult:
        """Ensure mission speed is plausible and within vehicle limits (if available)."""
        if not hasattr(self.mission, "speed") or self.mission.speed is None:
            return CheckResult(
                name="Mission Speed",
                status=CheckStatus.SKIP,
                message="No mission speed provided",
            )

        v_cmd = float(self.mission.speed)
        v_max = getattr(self.v, "speed_max_mps", None)
        v_cruise = getattr(self.v, "cruise_speed_mps", None)

        if v_max is not None and v_cmd > float(v_max):
            return CheckResult(
                name="Mission Speed",
                status=CheckStatus.FAIL,
                message=f"{v_cmd:.1f}m/s > max {float(v_max):.1f}m/s",
            )

        if v_cruise is not None and v_cmd < 0.3 * float(v_cruise):
            return CheckResult(
                name="Mission Speed",
                status=CheckStatus.WARN,
                message=f"{v_cmd:.1f}m/s unusually low vs cruise {float(v_cruise):.1f}m/s",
            )

        return CheckResult(
            name="Mission Speed", status=CheckStatus.PASS, message=f"{v_cmd:.1f} m/s"
        )

    def check_waypoint_count_limit(self) -> CheckResult:
        """Guard against FC mission-item limits / upload issues."""
        wps = getattr(self.mission, "waypoints", None)
        if not wps:
            return CheckResult(
                name="Waypoint Count", status=CheckStatus.SKIP, message="No waypoints"
            )
        max_wps = int(self._thr("MAX_WAYPOINTS", 700))
        if len(wps) > max_wps:
            return CheckResult(
                name="Waypoint Count",
                status=CheckStatus.FAIL,
                message=f"{len(wps)} > {max_wps}",
            )
        return CheckResult(name="Waypoint Count", status=CheckStatus.PASS, message=f"{len(wps)}")

    def check_agl_envelope_basic(self) -> CheckResult:
        """For missions with altitude_agl, enforce envelope."""
        agl = getattr(self.mission, "altitude_agl", None)
        if agl is None:
            return CheckResult(
                name="AGL Envelope",
                status=CheckStatus.SKIP,
                message="No altitude_agl on mission",
            )
        if float(agl) < float(self.AGL_MIN):
            return CheckResult(
                name="AGL Envelope",
                status=CheckStatus.FAIL,
                message=f"AGL {agl}m < min {self.AGL_MIN}m",
            )
        if float(agl) > float(self.AGL_MAX):
            return CheckResult(
                name="AGL Envelope",
                status=CheckStatus.FAIL,
                message=f"AGL {agl}m > max {self.AGL_MAX}m",
            )
        return CheckResult(name="AGL Envelope", status=CheckStatus.PASS, message=f"AGL {agl}m")

    def check_max_range_from_home(self) -> CheckResult:
        """Ensure mission remains within a max radius from home (if home known)."""
        pts = self._mission_points()
        if not pts:
            return CheckResult(
                name="Max Range From Home",
                status=CheckStatus.SKIP,
                message="No mission points",
            )

        home_lat = getattr(self.v, "home_lat", None)
        home_lon = getattr(self.v, "home_lon", None)
        if home_lat is None or home_lon is None:
            return CheckResult(
                name="Max Range From Home",
                status=CheckStatus.SKIP,
                message="Home location not available",
            )

        max_range_m = float(self._thr("MAX_RANGE_M", 5000.0))
        worst = 0.0
        for lat, lon in pts:
            d_m = self._haversine_m(float(home_lat), float(home_lon), lat, lon)
            worst = max(worst, d_m)

        if worst > max_range_m:
            enforce = bool(self._thr("ENFORCE_PREFLIGHT_RANGE", True))
            status = CheckStatus.FAIL if enforce else CheckStatus.WARN
            detail = "" if enforce else " (enforcement disabled)"
            return CheckResult(
                name="Max Range From Home",
                status=status,
                message=f"{worst:.0f}m > {max_range_m:.0f}m{detail}",
            )
        return CheckResult(
            name="Max Range From Home", status=CheckStatus.PASS, message=f"{worst:.0f}m"
        )

    def check_geofence_containment(self) -> CheckResult:
        """Validate mission points are inside ctx.geofence_polygon (if provided)."""
        raw_poly = getattr(self.ctx, "geofence_polygon", None)
        if not raw_poly:
            return CheckResult(
                name="Geofence Containment",
                status=CheckStatus.SKIP,
                message="No geofence polygon",
            )
        poly = self._normalize_polygon(raw_poly)
        if len(poly) < 3:
            return CheckResult(
                name="Geofence Containment",
                status=CheckStatus.FAIL,
                message="Invalid geofence polygon",
            )

        pts = self._mission_points()
        if not pts:
            return CheckResult(
                name="Geofence Containment",
                status=CheckStatus.SKIP,
                message="No mission points",
            )

        for i, (lat, lon) in enumerate(pts):
            if not self._point_in_polygon(lat, lon, poly):
                return CheckResult(
                    name="Geofence Containment",
                    status=CheckStatus.FAIL,
                    message=f"Point {i} outside geofence",
                )
        return CheckResult(
            name="Geofence Containment",
            status=CheckStatus.PASS,
            message="All mission points inside",
        )

    def check_no_fly_zones(self) -> CheckResult:
        """Validate mission points are not inside NFZ buffers (if ctx implements it)."""
        nfz = getattr(self.ctx, "no_fly_zones", None)
        if not nfz:
            return CheckResult(name="No-Fly Zones", status=CheckStatus.SKIP, message="No NFZ data")
        if not hasattr(self.ctx, "check_no_fly_zones"):
            return CheckResult(
                name="No-Fly Zones",
                status=CheckStatus.WARN,
                message="NFZ present but ctx.check_no_fly_zones not implemented",
            )

        buffer_m = float(self.ctx.get_threshold("NFZ_BUFFER_M", 50.0))
        pts = self._mission_points()
        if not pts:
            return CheckResult(
                name="No-Fly Zones",
                status=CheckStatus.SKIP,
                message="No mission points",
            )

        for i, (lat, lon) in enumerate(pts):
            if not self.ctx.check_no_fly_zones(lat, lon, buffer_m):
                return CheckResult(
                    name="No-Fly Zones",
                    status=CheckStatus.FAIL,
                    message=f"Point {i} inside/near NFZ (buffer {buffer_m:.0f}m)",
                )
        return CheckResult(
            name="No-Fly Zones",
            status=CheckStatus.PASS,
            message=f"Buffer {buffer_m:.0f}m OK",
        )

    def check_basic_terrain_clearance(self) -> CheckResult:
        """Generic clearance check using cached waypoint terrain (if available)."""
        wps = getattr(self.mission, "waypoints", None)
        if not wps:
            return CheckResult(
                name="Terrain Clearance",
                status=CheckStatus.SKIP,
                message="No waypoints",
            )
        if not hasattr(self.ctx, "get_waypoint_terrain"):
            return CheckResult(
                name="Terrain Clearance",
                status=CheckStatus.SKIP,
                message="No cached terrain in context",
            )

        min_clearance = float(self.ctx.get_threshold("MIN_CLEARANCE_M", 5.0))
        for i, wp in enumerate(wps):
            terrain = self._get_terrain(i)
            if terrain is None:
                return CheckResult(
                    name="Terrain Clearance",
                    status=CheckStatus.WARN,
                    message=f"Terrain missing at waypoint {i}",
                )
            alt = getattr(wp, "alt", None)
            if alt is None:
                return CheckResult(
                    name="Terrain Clearance",
                    status=CheckStatus.WARN,
                    message=f"Waypoint {i} missing alt",
                )
            clearance = float(alt) - float(terrain)
            if clearance < min_clearance:
                return CheckResult(
                    name="Terrain Clearance",
                    status=CheckStatus.FAIL,
                    message=f"WP{i} clearance {clearance:.1f}m < {min_clearance:.1f}m",
                )
        return CheckResult(
            name="Terrain Clearance",
            status=CheckStatus.PASS,
            message=f"Min clearance >= {min_clearance:.1f}m",
        )

    def check_grid_turn_margin(self) -> CheckResult:
        """Grid missions: approximate row-end turning feasibility based on spacing and speed."""
        if not hasattr(self.mission, "speed") or self.mission.speed is None:
            return CheckResult(
                name="Grid Turn Margin",
                status=CheckStatus.SKIP,
                message="No mission speed",
            )
        spacing = getattr(self.mission, "line_spacing_m", None)
        if spacing is None:
            return CheckResult(
                name="Grid Turn Margin",
                status=CheckStatus.SKIP,
                message="No line_spacing_m",
            )

        v = float(self.mission.speed)
        bank_max = float(self.BANK_MAX_DEG)
        g = 9.81
        # min radius from bank angle limit
        min_r = v * v / (g * math.tan(math.radians(bank_max)) + 1e-9)
        # crude available radius ~ half spacing (U-turn in corridor)
        avail_r = 0.5 * float(spacing)

        if avail_r <= 0:
            return CheckResult(
                name="Grid Turn Margin",
                status=CheckStatus.SKIP,
                message="Invalid spacing",
            )

        if avail_r < 0.8 * min_r:
            return CheckResult(
                name="Grid Turn Margin",
                status=CheckStatus.FAIL,
                message=f"Avail R~{avail_r:.1f}m < min {min_r:.1f}m (bank {bank_max:.0f}°)",
            )
        if avail_r < min_r:
            return CheckResult(
                name="Grid Turn Margin",
                status=CheckStatus.WARN,
                message=f"Avail R~{avail_r:.1f}m slightly < min {min_r:.1f}m",
            )
        return CheckResult(
            name="Grid Turn Margin",
            status=CheckStatus.PASS,
            message=f"Avail R~{avail_r:.1f}m, min {min_r:.1f}m",
        )

    def check_preflight_range(self) -> CheckResult:
        """Range check over the full clicked route."""
        from backend.core.config.runtime import settings

        # FIX (Bug 1 & 2): method previously required `home` and `route` as
        # positional arguments but was called with no arguments at the call site.
        # Both values are available on the context/vehicle_state, so derive them
        # here instead of requiring the caller to pass them.
        home_lat = getattr(self.v, "home_lat", None)
        home_lon = getattr(self.v, "home_lon", None)
        if home_lat is None or home_lon is None:
            return CheckResult(
                name="Preflight Range",
                status=CheckStatus.SKIP,
                message="Home location not available; skipping range check",
            )
        home = Coordinate(lat=float(home_lat), lon=float(home_lon), alt=0.0)
        route: list[Coordinate] = list(getattr(self.mission, "waypoints", []) or [])
        if not route:
            return CheckResult(
                name="Preflight Range",
                status=CheckStatus.SKIP,
                message="No route waypoints; skipping range check",
            )

        distance_km = self._total_route_distance_m(home, route) / 1000

        # FIX (Bug 3): original code imported Orchestrator as `orch` and then
        # called `orch.drone.get_telemetry()` — which uses the *class* object,
        # not an instance, and would raise AttributeError.  The vehicle state
        # (telemetry snapshot) is already available as self.v.
        t = self.v
        battery_remaining = getattr(t, "battery_remaining", None)
        level_frac = (
            None
            if battery_remaining is None
            else max(0.0, min(1.0, float(battery_remaining) / 100.0))
        )

        est_range_km = self.range_model.estimate_range_km(
            capacity_Wh=settings.battery_capacity_wh,
            battery_level_frac=level_frac,
            cruise_power_W=settings.cruise_power_w,
            cruise_speed_mps=settings.cruise_speed_mps,
            reserve_frac=settings.energy_reserve_frac,
        )

        feasible = (est_range_km is not None) and (est_range_km >= distance_km)

        if est_range_km is None:
            return CheckResult(
                name="Preflight Range",
                status=CheckStatus.WARN,
                message="No battery level reading; cannot estimate range",
            )

        # FIX (Bug 5): original code always returned CheckStatus.PASS regardless
        # of whether `feasible` was True or False.
        if not feasible:
            return CheckResult(
                name="Preflight Range",
                status=CheckStatus.FAIL,
                message=f"Insufficient range. Need ~{distance_km:.2f} km, est range {est_range_km:.2f} km.",
            )

        return CheckResult(
            name="Preflight Range",
            status=CheckStatus.PASS,
            message=f"Est range {est_range_km:.2f} km >= mission distance {distance_km:.2f} km",
        )

    async def run(self) -> list[CheckResult]:
        return [
            CheckResult(
                name="Mission Type",
                status=CheckStatus.WARN,
                message="No mission-specific checks registered",
            )
        ]


class WaypointMissionPreflight(MissionPreflightBase):
    """Generic waypoint-route mission (non-grid/orbit/patrol) checks."""

    async def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        results.append(self.check_waypoint_count_limit())
        results.append(self.check_speed_limits())
        results.append(self.check_max_range_from_home())
        results.append(self.check_geofence_containment())
        results.append(self.check_no_fly_zones())
        results.append(self.check_basic_terrain_clearance())
        results.append(self.check_preflight_range())  # check parameters
        return results


class GridMissionPreflight(MissionPreflightBase):
    """Grid/Survey mission preflight checks."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        # Type cast for IDE support
        self.mission: GridMission = context.mission

    def check_camera_footprint(self) -> CheckResult:
        """Check if line spacing is compatible with camera footprint."""
        if not hasattr(self.mission, "camera") or not self.mission.camera:
            return CheckResult(
                name="Grid Camera Footprint",
                status=CheckStatus.SKIP,
                message="No camera specifications provided",
            )

        camera = self.mission.camera
        agl = self.mission.altitude_agl

        # Calculate footprints
        footprint_width_m = 2 * agl * tan(radians(camera.fov_h / 2))
        footprint_height_m = 2 * agl * tan(radians(camera.fov_v / 2))

        issues = []

        # Check along-track spacing
        max_along_track = footprint_height_m * (1 - camera.front_overlap)
        if self.mission.along_track_spacing > max_along_track:
            issues.append(
                f"Along-track spacing {self.mission.along_track_spacing:.1f}m > "
                f"max {max_along_track:.1f}m"
            )

        # Check cross-track spacing
        max_cross_track = footprint_width_m * (1 - camera.side_overlap)
        if self.mission.cross_track_spacing > max_cross_track:
            issues.append(
                f"Cross-track spacing {self.mission.cross_track_spacing:.1f}m > "
                f"max {max_cross_track:.1f}m"
            )

        if issues:
            return CheckResult(
                name="Grid Camera Footprint",
                status=CheckStatus.FAIL,
                message="; ".join(issues),
            )

        return CheckResult(
            name="Grid Camera Footprint",
            status=CheckStatus.PASS,
            message=f"Footprint: {footprint_width_m:.1f}×{footprint_height_m:.1f}m",
        )

    def check_mission_duration(self) -> CheckResult:
        """Check if mission duration is within vehicle limits."""
        total_distance = self.ctx.total_distance()
        flight_time_s = total_distance / self.mission.speed if self.mission.speed > 0 else 0

        # Add turn penalties
        if hasattr(self.mission, "grid_segments") and self.mission.grid_segments:
            num_turns = len(self.mission.grid_segments) - 1
            flight_time_s += self.TURN_PENALTY_S * num_turns

        if hasattr(self.v, "max_flight_time_s") and self.v.max_flight_time_s:
            if flight_time_s > self.v.max_flight_time_s:
                return CheckResult(
                    name="Grid Duration",
                    status=CheckStatus.FAIL,
                    message=f"Est. time {flight_time_s / 60:.1f}min > "
                    f"max {self.v.max_flight_time_s / 60:.1f}min",
                )

        return CheckResult(
            name="Grid Duration",
            status=CheckStatus.PASS,
            message=f"Est. time: {flight_time_s / 60:.1f}min",
        )

    async def run(self) -> list[CheckResult]:
        """Run all grid mission checks."""
        results: list[CheckResult] = []
        # Common mission-specific safety/validity checks
        results.append(self.check_waypoint_count_limit())
        results.append(self.check_speed_limits())
        results.append(self.check_agl_envelope_basic())
        results.append(self.check_max_range_from_home())
        results.append(self.check_geofence_containment())
        results.append(self.check_no_fly_zones())
        results.append(self.check_basic_terrain_clearance())
        results.append(self.check_grid_turn_margin())

        # Grid-specific payload/coverage checks
        results.append(self.check_camera_footprint())
        results.append(self.check_mission_duration())
        return results


class TerrainFollowMissionPreflight(MissionPreflightBase):
    """Terrain-following mission checks using context."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: TerrainFollowMission = context.mission

    def check_terrain_follow_feasibility(self) -> list[CheckResult]:
        """Validate terrain-follow climb/descent rates using cached/precomputed terrain only."""
        if len(self.mission.waypoints) < 2:
            return [
                CheckResult(
                    name="Terrain Follow",
                    status=CheckStatus.FAIL,
                    message="At least two waypoints are required",
                )
            ]

        speed = float(getattr(self.mission, "speed", 0.0) or 0.0)

        if speed <= 0:
            return [
                CheckResult(
                    name="Terrain Follow",
                    status=CheckStatus.FAIL,
                    message="Mission speed must be positive",
                )
            ]

        max_climb_rate = 0.0
        max_descent_rate = 0.0
        missing_terrain: list[int] = []

        for i in range(1, len(self.mission.waypoints)):
            current_terrain = self._get_terrain(i)
            previous_terrain = self._get_terrain(i - 1)

            if current_terrain is None or previous_terrain is None:
                missing_terrain.append(i)
                continue

            segment_distance = self._get_distance(i - 1, i)

            if segment_distance <= 0:
                continue

            segment_time = segment_distance / speed

            # Constant AGL terrain-follow means required vehicle altitude changes by terrain delta only.
            rate = (float(current_terrain) - float(previous_terrain)) / segment_time

            if rate >= 0:
                max_climb_rate = max(max_climb_rate, rate)
            else:
                max_descent_rate = max(max_descent_rate, abs(rate))

        if missing_terrain:
            return [
                CheckResult(
                    name="Terrain Follow",
                    status=CheckStatus.WARN,
                    message=f"Terrain missing at waypoint(s): {missing_terrain[:5]}",
                )
            ]

        results: list[CheckResult] = []

        climb_rate_max = float(getattr(self.v, "climb_rate_max", 5.0) or 5.0)
        descent_rate_max = float(getattr(self.v, "descent_rate_max", 3.0) or 3.0)

        results.append(
            CheckResult(
                name="Climb Rate",
                status=CheckStatus.PASS if max_climb_rate <= climb_rate_max else CheckStatus.FAIL,
                message=f"Required {max_climb_rate:.1f}m/s, max {climb_rate_max:.1f}m/s",
            )
        )

        results.append(
            CheckResult(
                name="Descent Rate",
                status=CheckStatus.PASS if max_descent_rate <= descent_rate_max else CheckStatus.FAIL,
                message=f"Required {max_descent_rate:.1f}m/s, max {descent_rate_max:.1f}m/s",
            )
        )

        return results

    async def run(self) -> list[CheckResult]:
        """Run all terrain-following mission checks."""
        results: list[CheckResult] = []
        results.append(self.check_waypoint_count_limit())
        results.append(self.check_speed_limits())
        results.append(self.check_max_range_from_home())
        results.append(self.check_geofence_containment())
        results.append(self.check_no_fly_zones())
        # terrain-follow includes its own climb/descent feasibility and uses cached terrain
        results.extend(self.check_terrain_follow_feasibility())
        return results


class OrbitMissionPreflight(MissionPreflightBase):
    """Orbit / POI mission preflight checks."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: OrbitMission = context.mission

    def check_turn_feasibility(self) -> list[CheckResult]:
        """Check both bank angle and lateral acceleration limits."""
        results = []

        v = self.mission.speed
        r = self.mission.radius
        g = 9.81

        # Calculate bank angle
        bank_rad = atan(v**2 / (r * g))
        bank_deg = bank_rad * 180 / pi

        # Calculate lateral acceleration
        a_lat = v**2 / r

        # Bank angle check
        if bank_deg <= self.BANK_MAX_DEG:
            results.append(
                CheckResult(
                    name="Orbit Bank Angle",
                    status=CheckStatus.PASS,
                    message=f"Bank: {bank_deg:.1f}° (max {self.BANK_MAX_DEG}°)",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Orbit Bank Angle",
                    status=CheckStatus.FAIL,
                    message=f"Bank angle {bank_deg:.1f}° > {self.BANK_MAX_DEG}°",
                )
            )

        # Lateral acceleration check
        if a_lat <= self.A_LAT_MAX:
            results.append(
                CheckResult(
                    name="Orbit Lateral Acceleration",
                    status=CheckStatus.PASS,
                    message=f"Lateral accel: {a_lat:.2f}m/s² (max {self.A_LAT_MAX}m/s²)",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Orbit Lateral Acceleration",
                    status=CheckStatus.FAIL,
                    message=f"Lateral accel {a_lat:.2f}m/s² > {self.A_LAT_MAX}m/s²",
                )
            )

        return results

    def check_clearance(self) -> CheckResult:
        """Check clearance around POI."""
        # Check minimum standoff
        if self.mission.radius < self.mission.min_standoff_m:
            return CheckResult(
                name="POI Clearance",
                status=CheckStatus.FAIL,
                message=f"Orbit radius {self.mission.radius}m < min standoff {self.mission.min_standoff_m}m",
            )

        # Check AGL if POI location has terrain
        if self.mission.poi_location:
            agl = self.mission.altitude_agl
            if agl < self.AGL_MIN or agl > self.AGL_MAX:
                return CheckResult(
                    name="Orbit AGL",
                    status=CheckStatus.WARN,
                    message=f"Orbit AGL {agl}m may be outside safe envelope ({self.AGL_MIN}-{self.AGL_MAX}m)",
                )

        return CheckResult(
            name="POI Clearance",
            status=CheckStatus.PASS,
            message=f"Radius: {self.mission.radius}m, Standoff OK",
        )

    async def run(self) -> list[CheckResult]:
        """Run all orbit mission checks."""
        results: list[CheckResult] = []
        results.append(self.check_speed_limits())
        results.append(self.check_max_range_from_home())
        results.append(self.check_geofence_containment())
        results.append(self.check_no_fly_zones())
        results.extend(self.check_turn_feasibility())
        results.append(self.check_clearance())
        return results


class PerimeterPatrolMissionPreflight(MissionPreflightBase):
    """Perimeter patrol (polygon follow) mission preflight checks."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: PerimeterPatrolMission = context.mission

    def check_polygon_validity(self) -> CheckResult:
        """Check if patrol polygon is valid."""
        if len(self.mission.polygon) < 3:
            return CheckResult(
                name="Polygon Validity",
                status=CheckStatus.FAIL,
                message=f"Polygon has {len(self.mission.polygon)} points, need at least 3",
            )

        # Polygon is already validated by Pydantic
        return CheckResult(
            name="Polygon Validity",
            status=CheckStatus.PASS,
            message=f"Polygon valid with {len(self.mission.polygon)} points",
        )

    def _calculate_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate initial bearing from point1 to point2 in radians."""
        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)
        dlon = math.radians(lon2 - lon1)

        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)

        bearing = math.atan2(y, x)
        return bearing

    def _calculate_turn_angle(self, p1: Waypoint, p2: Waypoint, p3: Waypoint) -> float:
        """Calculate turn angle at p2 using initial bearings."""
        # Calculate bearing from p1 to p2
        bearing1 = self._calculate_bearing(p1.lat, p1.lon, p2.lat, p2.lon)

        # Calculate bearing from p2 to p3
        bearing2 = self._calculate_bearing(p2.lat, p2.lon, p3.lat, p3.lon)

        # Calculate the absolute difference in bearings
        angle_diff = abs(bearing2 - bearing1)

        # Normalize to [0, π]
        if angle_diff > math.pi:
            angle_diff = 2 * math.pi - angle_diff

        return angle_diff

    def check_cornering_limits(self) -> CheckResult:
        """Check if cornering is feasible given turn constraints."""
        if not hasattr(self.mission, "polygon") or len(self.mission.polygon) < 3:
            return CheckResult(
                name="Cornering Limits",
                status=CheckStatus.SKIP,
                message="Insufficient polygon data",
            )

        v = getattr(self.mission, "speed", getattr(self.v, "cruise_speed_mps", 10))
        max_turn_rate = getattr(self.v, "max_turn_rate_rad_s", 0.5)

        # Calculate minimum turn radius from max turn rate
        # turn_rate = v / r  => r_min = v / max_turn_rate
        r_min = v / max_turn_rate if max_turn_rate > 0 else float("inf")

        # Also check against max lateral acceleration
        a_lat_max = getattr(self, "A_LAT_MAX", 9.81)
        r_min_accel = v**2 / a_lat_max
        r_min = max(r_min, r_min_accel)

        # Check each corner
        tight_corners = []
        polygon = self.mission.polygon

        # Use all corners (including closing the loop)
        for i in range(len(polygon)):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % len(polygon)]
            p3 = polygon[(i + 2) % len(polygon)]

            # Calculate turn angle at p2
            turn_angle = self._calculate_turn_angle(p1, p2, p3)

            # Skip if nearly straight (angle close to 0 or π)
            if turn_angle < 0.05 or turn_angle > math.pi - 0.05:
                continue

            # Calculate chord length (distance from p2 to p3)
            p2 = polygon[(i + 1) % len(polygon)]
            p3 = polygon[(i + 2) % len(polygon)]
            chord_length = self.ctx.get_distance_between_points(p2, p3)

            # For a given turn angle, the required radius can be estimated
            if turn_angle > 0:
                # Required radius to make this turn at current speed
                required_radius = chord_length / (2 * math.sin(turn_angle / 2))

                if required_radius < r_min:
                    tight_corners.append(
                        {
                            "corner": i,
                            "turn_angle_deg": math.degrees(turn_angle),
                            "required_radius": required_radius,
                            "chord_length": chord_length,
                        }
                    )

        if tight_corners:
            # Sort by most severe
            tight_corners.sort(key=lambda x: x["required_radius"])
            worst = tight_corners[0]

            message = (
                f"{len(tight_corners)} corners exceed turn limits. "
                f"Worst: corner {worst['corner']} requires {worst['required_radius']:.1f}m radius "
                f"(min {r_min:.1f}m), turn angle {worst['turn_angle_deg']:.1f}°"
            )

            return CheckResult(name="Cornering Limits", status=CheckStatus.FAIL, message=message)

        return CheckResult(
            name="Cornering Limits",
            status=CheckStatus.PASS,
            message=f"All corners within turn limits (min radius {r_min:.1f}m)",
        )

    def check_boundary_buffer(self) -> CheckResult:
        """Check if path maintains safe buffer from boundary."""
        if self.mission.path_offset_m < self.mission.boundary_buffer_min:
            return CheckResult(
                name="Boundary Buffer",
                status=CheckStatus.FAIL,
                message=f"Path offset {self.mission.path_offset_m}m < min buffer {self.mission.boundary_buffer_min}m",
            )

        return CheckResult(
            name="Boundary Buffer",
            status=CheckStatus.PASS,
            message=f"Buffer: {self.mission.path_offset_m}m (min {self.mission.boundary_buffer_min}m)",
        )

    async def run(self) -> list[CheckResult]:
        """Run all perimeter patrol checks."""
        results: list[CheckResult] = []
        results.append(self.check_polygon_validity())
        results.append(self.check_speed_limits())
        results.append(self.check_agl_envelope_basic())
        results.append(self.check_max_range_from_home())
        results.append(self.check_geofence_containment())
        results.append(self.check_no_fly_zones())
        results.append(self.check_boundary_buffer())
        results.append(self.check_cornering_limits())
        return results


class AdaptiveAltitudeMissionPreflight(MissionPreflightBase):
    """Adaptive altitude over elevation models preflight checks."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: AdaptiveAltitudeMission = context.mission

    def check_altitude_limits(self) -> list[CheckResult]:
        """Check if commanded altitudes are within limits."""
        results = []

        for i, _ in enumerate(self.mission.waypoints):
            terrain = self._get_terrain(i) or 0
            cmd_alt = terrain + self.mission.target_agl

            if cmd_alt > self.mission.alt_ceiling_msl:
                results.append(
                    CheckResult(
                        name=f"Waypoint {i} Altitude",
                        status=CheckStatus.FAIL,
                        message=f"Altitude {cmd_alt}m > ceiling {self.mission.alt_ceiling_msl}m",
                    )
                )
            elif cmd_alt < self.mission.alt_floor_msl:
                results.append(
                    CheckResult(
                        name=f"Waypoint {i} Altitude",
                        status=CheckStatus.FAIL,
                        message=f"Altitude {cmd_alt}m < floor {self.mission.alt_floor_msl}m",
                    )
                )

        if not results:
            results.append(
                CheckResult(
                    name="Altitude Limits",
                    status=CheckStatus.PASS,
                    message="All altitudes within limits",
                )
            )

        return results

    def check_agl_envelope(self) -> CheckResult:
        """Check if AGL values are within safety envelope."""
        for i, wp in enumerate(self.mission.waypoints):
            terrain = self._get_terrain(i)
            if terrain is not None:
                # Compute actual AGL: waypoint altitude minus terrain elevation
                agl = wp.alt - terrain
                if agl < self.mission.agl_min or agl > self.mission.agl_max:
                    return CheckResult(
                        name="AGL Envelope",
                        status=CheckStatus.FAIL,
                        message=f"Waypoint {i} AGL {agl:.1f}m outside envelope [{self.mission.agl_min}, {self.mission.agl_max}]m",
                    )

        return CheckResult(
            name="AGL Envelope",
            status=CheckStatus.PASS,
            message=f"Target AGL {self.mission.target_agl}m within envelope",
        )

    async def run(self) -> list[CheckResult]:
        """Run all adaptive altitude checks."""
        results: list[CheckResult] = []
        results.append(self.check_waypoint_count_limit())
        results.append(self.check_speed_limits())
        results.append(self.check_max_range_from_home())
        results.append(self.check_geofence_containment())
        results.append(self.check_no_fly_zones())
        results.extend(self.check_altitude_limits())
        results.append(self.check_agl_envelope())
        return results


class WarehouseScanMissionPreflight(MissionPreflightBase):
    """Indoor warehouse scan checks for local-frame navigation and corridor geometry."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: WarehouseScanMission = context.mission

    def check_local_origin(self) -> CheckResult:
        origin = getattr(self.mission, "local_origin", None)
        if origin is None:
            return CheckResult(
                name="Warehouse Local Origin",
                status=CheckStatus.FAIL,
                message="No local warehouse origin was defined",
            )
        lat = getattr(origin, "lat", None)
        lon = getattr(origin, "lon", None)
        if lat is None or lon is None:
            return CheckResult(
                name="Warehouse Local Origin",
                status=CheckStatus.PASS,
                message="Origin defined in local warehouse frame",
            )
        return CheckResult(
            name="Warehouse Local Origin",
            status=CheckStatus.PASS,
            message=f"Origin locked at ({float(lat):.6f}, {float(lon):.6f})",
        )

    def _perception_status(self) -> dict[str, Any]:
        status = self.ctx.config_overrides.get("WAREHOUSE_PERCEPTION_STATUS")
        return status if isinstance(status, dict) else {}

    def _perception_components(self) -> dict[str, Any]:
        components = self._perception_status().get("components")
        return components if isinstance(components, dict) else {}

    def _component_bool(self, *keys: str) -> bool | None:
        components = self._perception_components()
        for key in keys:
            value = components.get(key)
            if isinstance(value, bool):
                return value
            if isinstance(value, dict):
                nested = value.get("ready", value.get("healthy", value.get("ok")))
                if isinstance(nested, bool):
                    return nested
        return None

    def _topic_configured(self, *keys: str) -> bool:
        topics = self._perception_components().get("topics")
        if not isinstance(topics, dict):
            return False
        for key in keys:
            topic = topics.get(key)
            if not isinstance(topic, str) or not topic.strip():
                return False
        return True

    def _component_check(
        self,
        *,
        name: str,
        keys: tuple[str, ...],
        pass_message: str,
        fail_message: str,
    ) -> CheckResult:
        value = self._component_bool(*keys)
        if value is True:
            return CheckResult(name=name, status=CheckStatus.PASS, message=pass_message)
        if value is False:
            return CheckResult(name=name, status=CheckStatus.FAIL, message=fail_message)
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"{name} status is missing from the ROS bridge health payload",
        )

    def _topic_diagnostic(self, key: str) -> dict[str, Any] | None:
        components = self._perception_components()
        diagnostics = components.get("topic_diagnostics")
        if isinstance(diagnostics, dict):
            diag = diagnostics.get(key)
            if isinstance(diag, dict):
                return diag
        matches = components.get("topic_matches")
        if isinstance(matches, dict):
            diag = matches.get(key)
            if isinstance(diag, dict):
                return diag
        return None

    def _topic_diagnostic_message(self, key: str) -> str | None:
        diag = self._topic_diagnostic(key)
        if not diag:
            return None
        expected = diag.get("expected")
        matched = diag.get("matched")
        error = diag.get("error")
        if error:
            return f"expected={expected} matched={matched or 'none'} ({error})"
        if not diag.get("healthy"):
            return f"expected={expected} matched={matched or 'none'}"
        return None

    def _tf_chain_detail(self) -> str | None:
        components = self._perception_components()
        tf_chain = components.get("tf_chain")
        if isinstance(tf_chain, dict):
            detail = tf_chain.get("detail")
            if isinstance(detail, str) and detail.strip() and detail != "ok":
                return detail.strip()
        return None

    def _missing_topics_message(self, *, prefix: str) -> str:
        components = self._perception_components()
        missing = components.get("missing_required_topics")
        if isinstance(missing, list) and missing:
            return f"{prefix}: {', '.join(str(item) for item in missing)}"
        detail = self._perception_status().get("detail")
        if isinstance(detail, str) and detail.strip():
            return f"{prefix}. {detail.strip()}"
        return prefix

    def _warehouse_sensor_readiness(self):
        status_dict = self._perception_status()
        if not status_dict:
            return None

        class _Readiness:
            ready = bool(status_dict.get("ready"))
            detail = status_dict.get("detail") if isinstance(status_dict.get("detail"), str) else None

        return _Readiness()

    def check_ros_bridge(self) -> CheckResult:
        status = self._perception_status()
        if not status:
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.FAIL,
                message="Warehouse ROS bridge health was not collected",
            )
        if not bool(status.get("configured")):
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.FAIL,
                message="Warehouse ROS bridge URL is not configured",
            )
        if not bool(status.get("reachable")):
            detail = status.get("detail")
            suffix = f": {detail}" if isinstance(detail, str) and detail else ""
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.FAIL,
                message=f"Jetson ROS bridge is unreachable{suffix}",
            )
        if bool(status.get("ready")):
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.PASS,
                message=f"Jetson bridge ready ({status.get('profile') or 'unknown profile'})",
            )
        takeoff = self._warehouse_sensor_readiness()
        if takeoff is not None and takeoff.ready:
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.PASS,
                message=(
                    f"Bridge reachable; required sensor topics are live "
                    f"({status.get('profile') or 'unknown profile'})"
                ),
            )
        bridge_status = status.get("status") or "not ready"
        detail = takeoff.detail if takeoff is not None and takeoff.detail else None
        prefix = f"Jetson ROS bridge status is {bridge_status}"
        if detail:
            prefix = f"{prefix}: {detail}"
        return CheckResult(
            name="Warehouse ROS Bridge",
            status=CheckStatus.FAIL,
            message=self._missing_topics_message(prefix=prefix),
        )

    def check_ros_graph(self) -> CheckResult:
        value = self._component_bool("ros_graph", "ros2_graph", "ros2_cli")
        if value is True:
            return CheckResult(
                name="Warehouse ROS Graph",
                status=CheckStatus.PASS,
                message="ROS 2 graph is available",
            )
        if value is False:
            return CheckResult(
                name="Warehouse ROS Graph",
                status=CheckStatus.FAIL,
                message="ROS 2 graph or ros2 CLI is unavailable on the Jetson",
            )
        return CheckResult(
            name="Warehouse ROS Graph",
            status=CheckStatus.FAIL,
            message="ROS 2 graph health is missing from the bridge payload",
        )

    def check_camera_topics(self) -> CheckResult:
        if self._component_bool("camera_topics", "stereo_camera") is True:
            return CheckResult(
                name="Warehouse Camera Topics",
                status=CheckStatus.PASS,
                message="Camera topics are publishing",
            )
        rgb_diag = self._topic_diagnostic("rgb_image")
        if rgb_diag and (
            rgb_diag.get("healthy")
            or rgb_diag.get("readiness_state") in {"ok", "ok_via_messages", "shallow_present"}
        ):
            matched = rgb_diag.get("matched") or rgb_diag.get("expected")
            return CheckResult(
                name="Warehouse Camera Topics",
                status=CheckStatus.PASS,
                message=f"RGB camera topic listed ({matched})",
            )
        detail = self._topic_diagnostic_message("rgb_image")
        if detail is None:
            left_detail = self._topic_diagnostic_message("left_image")
            right_detail = self._topic_diagnostic_message("right_image")
            if left_detail or right_detail:
                detail = "; ".join(filter(None, [left_detail, right_detail]))
        return CheckResult(
            name="Warehouse Camera Topics",
            status=CheckStatus.FAIL,
            message=detail or "RGB or stereo camera topics are not publishing",
        )

    def check_stereo_sync(self) -> CheckResult:
        value = self._component_bool("stereo_sync", "stereo_timestamps_synced")
        if value is True:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.PASS,
                message="Stereo timestamps are synchronized",
            )
        if value is False:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.FAIL,
                message="Stereo timestamps are not synchronized",
            )

        rgb_diag = self._topic_diagnostic("rgb_image")
        rgb_ok = bool(
            rgb_diag
            and (
                rgb_diag.get("healthy")
                or rgb_diag.get("readiness_state")
                in {"ok", "ok_via_messages", "ok_graph_presence", "shallow_present"}
            )
        )
        left_diag = self._topic_diagnostic("left_image")
        right_diag = self._topic_diagnostic("right_image")
        stereo_topics_present = bool(left_diag or right_diag)

        if rgb_ok and not stereo_topics_present:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.SKIP,
                message="RGBD front camera in use; stereo pair sync not required",
            )

        if rgb_ok:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.PASS,
                message="RGB camera live; stereo sync not reported (RGBD mode)",
            )

        sim_mode = _warehouse_sim_mode()
        if sim_mode:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.WARN,
                message=(
                    "Stereo sync not reported by bridge; verify left/right topics if using stereo"
                ),
            )

        return CheckResult(
            name="Warehouse Stereo Sync",
            status=CheckStatus.FAIL,
            message="Warehouse Stereo Sync status is missing from the ROS bridge health payload",
        )

    def check_imu_topic(self) -> CheckResult:
        if self._component_bool("imu_healthy", "imu_topic", "imu") is True:
            return CheckResult(
                name="Warehouse IMU Topic",
                status=CheckStatus.PASS,
                message="IMU topic is publishing",
            )
        detail = self._topic_diagnostic_message("imu")
        return CheckResult(
            name="Warehouse IMU Topic",
            status=CheckStatus.FAIL,
            message=detail or "IMU topic is not publishing",
        )

    def check_tf_tree(self) -> CheckResult:
        if self._component_bool("tf_tree", "tf", "tf_static") is True:
            return CheckResult(
                name="Warehouse TF Tree",
                status=CheckStatus.PASS,
                message="Required TF chain odom→base_link→camera is valid",
            )
        detail = self._tf_chain_detail()
        return CheckResult(
            name="Warehouse TF Tree",
            status=CheckStatus.FAIL,
            message=detail or "Required TF frames are missing or disconnected (odom/base_link/camera)",
        )

    def check_visual_slam(self) -> CheckResult:
        if self._component_bool(
            "visual_slam_healthy",
            "visual_slam",
            "vslam",
            "visual_slam_tracking",
        ):
            return CheckResult(
                name="Warehouse Visual SLAM",
                status=CheckStatus.PASS,
                message="Visual SLAM odometry is publishing and fresh",
            )
        if self._component_bool("odometry_state_unreadable"):
            topic = self._perception_components().get("odometry_topic") or "/warehouse/drone/odometry"
            return CheckResult(
                name="Warehouse Local Odometry",
                status=CheckStatus.FAIL,
                message=(
                    f"Local odometry state unreadable; verify publishing on {topic} "
                    "(single-message sensor sample)"
                ),
            )
        for key in ("visual_slam_odom", "local_odometry"):
            diag = self._topic_diagnostic(key)
            if diag and (
                diag.get("healthy")
                or diag.get("readiness_state") in {"ok", "ok_via_messages", "shallow_present"}
            ):
                matched = diag.get("matched") or diag.get("expected")
                source = self._perception_components().get("odometry_source") or "local_odom"
                return CheckResult(
                    name="Warehouse Local Odometry",
                    status=CheckStatus.PASS,
                    message=f"{source} live ({matched})",
                )
        detail = self._topic_diagnostic_message("visual_slam_odom")
        topic = self._perception_components().get("odometry_topic") or "/warehouse/drone/odometry"
        return CheckResult(
            name="Warehouse Local Odometry",
            status=CheckStatus.FAIL,
            message=detail or f"Local odometry not ready (check {topic})",
        )

    def check_nvblox(self) -> CheckResult:
        if self._component_bool("nvblox_healthy", "nvblox", "nvblox_mapping"):
            return CheckResult(
                name="Warehouse Nvblox",
                status=CheckStatus.PASS,
                message="Nvblox mapping outputs are publishing and fresh",
            )
        components = self._perception_components()
        sim_mode = _warehouse_sim_mode()
        listed = components.get("listed_topics")
        has_nvblox_node = isinstance(listed, list) and any(
            str(topic).startswith("/nvblox_node/") for topic in listed
        )
        if components.get("nvblox_warming_up") or (sim_mode and has_nvblox_node):
            return CheckResult(
                name="Warehouse Nvblox",
                status=CheckStatus.WARN,
                message=(
                    "Nvblox is running; map outputs may still be warming up — "
                    "flight can start mapping in parallel"
                ),
            )
        strict_nvblox = os.getenv("WAREHOUSE_PREFLIGHT_WAIT_NVBLOX", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if sim_mode and not has_nvblox_node and not strict_nvblox:
            return CheckResult(
                name="Warehouse Nvblox",
                status=CheckStatus.WARN,
                message=(
                    "Nvblox is not running yet (starts when the warehouse flight begins); "
                    "Source transport sensor topics are sufficient for preflight"
                ),
            )
        missing = components.get("missing_nvblox_topics")
        detail_parts: list[str] = []
        if isinstance(missing, list) and missing:
            detail_parts.append(f"missing outputs: {', '.join(str(item) for item in missing)}")
        for key in ("pointcloud", "mesh", "mesh_marker", "occupancy", "esdf", "back_projected_depth"):
            diag_msg = self._topic_diagnostic_message(key)
            if diag_msg:
                detail_parts.append(f"{key}: {diag_msg}")
        return CheckResult(
            name="Warehouse Nvblox",
            status=CheckStatus.FAIL,
            message="; ".join(detail_parts) or "Nvblox mapping outputs are not ready",
        )

    def check_mapping_disk(self) -> CheckResult:
        components = self._perception_components()
        min_gb = float(self._thr("WAREHOUSE_MAPPING_DISK_FREE_GB_MIN", 10.0))
        raw_gb = components.get("disk_free_gb")
        if raw_gb is None and components.get("disk_free_bytes") is not None:
            raw_gb = float(components["disk_free_bytes"]) / 1_000_000_000.0
        if raw_gb is None:
            disk = components.get("disk")
            if isinstance(disk, dict):
                raw_gb = disk.get("free_gb")
        if raw_gb is None:
            return CheckResult(
                name="Warehouse Mapping Disk",
                status=CheckStatus.FAIL,
                message="Free capture disk space is missing from ROS bridge health",
            )
        free_gb = float(raw_gb)
        if free_gb < min_gb:
            return CheckResult(
                name="Warehouse Mapping Disk",
                status=CheckStatus.FAIL,
                message=f"Capture disk free {free_gb:.1f}GB < required {min_gb:.1f}GB",
            )
        return CheckResult(
            name="Warehouse Mapping Disk",
            status=CheckStatus.PASS,
            message=f"Capture disk free {free_gb:.1f}GB",
        )

    def check_sensor_rig(self) -> CheckResult:
        sensor_rig_id = getattr(self.mission, "sensor_rig_id", None)
        if sensor_rig_id is None:
            return CheckResult(
                name="Warehouse Sensor Rig",
                status=CheckStatus.FAIL,
                message="No calibrated sensor rig was selected for this scan",
            )
        return CheckResult(
            name="Warehouse Sensor Rig",
            status=CheckStatus.PASS,
            message=f"Sensor rig {sensor_rig_id} selected",
        )

    def check_battery_margin(self) -> CheckResult:
        reserve_pct = float(self._thr("WAREHOUSE_SCAN_BATTERY_RESERVE_PCT", 30.0))
        if reserve_pct <= 0:
            return CheckResult(
                name="Warehouse Battery Margin",
                status=CheckStatus.SKIP,
                message="Battery margin check disabled for ROS/sim warehouse preflight",
            )
        battery_pct = getattr(self.v, "battery_percent", None)
        if battery_pct is None:
            battery_pct = getattr(self.v, "battery_remaining", None)
        if battery_pct is None:
            return CheckResult(
                name="Warehouse Battery Margin",
                status=CheckStatus.SKIP,
                message="Battery percentage unavailable (MAVLink not required for warehouse sim)",
            )
        pct = float(battery_pct)
        if pct <= 1.0:
            pct *= 100.0
        if pct < reserve_pct:
            return CheckResult(
                name="Warehouse Battery Margin",
                status=CheckStatus.FAIL,
                message=f"Battery {pct:.0f}% < warehouse reserve {reserve_pct:.0f}%",
            )
        return CheckResult(
            name="Warehouse Battery Margin",
            status=CheckStatus.PASS,
            message=f"Battery {pct:.0f}% >= reserve {reserve_pct:.0f}%",
        )

    def check_dock_marker(self) -> CheckResult:
        marker_id = getattr(self.mission, "dock_marker_id", None)
        precision_required = bool(getattr(self.mission, "dock_precision_required", False))
        if not marker_id and not precision_required:
            return CheckResult(
                name="Warehouse Dock Marker",
                status=CheckStatus.SKIP,
                message="No precision dock marker required for this scan",
            )
        visible = self._component_bool("dock_marker", "apriltag", "dock_reference")
        if visible is True:
            return CheckResult(
                name="Warehouse Dock Marker",
                status=CheckStatus.PASS,
                message=f"Dock marker {marker_id or ''} visible".strip(),
            )
        if visible is False:
            return CheckResult(
                name="Warehouse Dock Marker",
                status=CheckStatus.FAIL,
                message="Required dock marker is not visible",
            )
        return CheckResult(
            name="Warehouse Dock Marker",
            status=CheckStatus.FAIL,
            message="Required dock marker visibility is missing from ROS bridge health",
        )

    def check_local_position_lock(self) -> CheckResult:
        local_ok = getattr(self.v, "local_position_ok", None)
        if local_ok is True:
            return CheckResult(
                name="Warehouse Local Position",
                status=CheckStatus.PASS,
                message="Vehicle local position is available",
            )
        if local_ok is False:
            return CheckResult(
                name="Warehouse Local Position",
                status=CheckStatus.FAIL,
                message="Vehicle local position is unavailable",
            )
        north = getattr(self.v, "local_north_m", None)
        east = getattr(self.v, "local_east_m", None)
        down = getattr(self.v, "local_down_m", None)
        if north is not None and east is not None and down is not None:
            return CheckResult(
                name="Warehouse Local Position",
                status=CheckStatus.PASS,
                message="Vehicle local position is populated",
            )
        return CheckResult(
            name="Warehouse Local Position",
            status=CheckStatus.FAIL,
            message="Warehouse missions require a valid local frame before launch",
        )

    def check_odometry_health(self) -> CheckResult:
        odometry_healthy = getattr(self.v, "odometry_healthy", None)
        max_drift_m = float(self._thr("WAREHOUSE_ODOMETRY_DRIFT_MAX_M", 0.75))
        drift_m = getattr(self.v, "odometry_drift_m", None)
        if odometry_healthy is False:
            return CheckResult(
                name="Warehouse Odometry",
                status=CheckStatus.FAIL,
                message="Vehicle odometry is unhealthy",
            )
        if drift_m is not None and float(drift_m) > max_drift_m:
            return CheckResult(
                name="Warehouse Odometry",
                status=CheckStatus.FAIL,
                message=f"Odometry drift {float(drift_m):.2f}m > {max_drift_m:.2f}m",
            )
        if odometry_healthy is True or drift_m is not None:
            detail = f"Drift {float(drift_m):.2f}m" if drift_m is not None else "Odometry healthy"
            return CheckResult(
                name="Warehouse Odometry",
                status=CheckStatus.PASS,
                message=detail,
            )
        return CheckResult(
            name="Warehouse Odometry",
            status=CheckStatus.WARN,
            message="Odometry health could not be verified from telemetry",
        )

    def check_lidar_health(self) -> CheckResult:
        components = self._perception_components()
        raw_lidar_healthy = components.get("raw_lidar_healthy")
        if raw_lidar_healthy is True:
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.PASS,
                message="LiDAR point cloud topic is publishing",
            )
        if raw_lidar_healthy is False:
            detail = self._topic_diagnostic_message("raw_lidar")
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.FAIL,
                message=detail or "LiDAR point cloud topic is not publishing",
            )

        lidar_healthy = getattr(self.v, "lidar_healthy", None)
        obstacle_distance_m = getattr(self.v, "obstacle_distance_m", None)
        clearance_m = float(getattr(self.mission, "clearance_m", 0.6))
        if lidar_healthy is False:
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.FAIL,
                message="LiDAR/range input is unhealthy",
            )
        if obstacle_distance_m is not None and float(obstacle_distance_m) < clearance_m:
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.FAIL,
                message=(
                    f"Obstacle distance {float(obstacle_distance_m):.2f}m is inside "
                    f"the required clearance {clearance_m:.2f}m"
                ),
            )
        if lidar_healthy is True:
            message = (
                f"Obstacle distance {float(obstacle_distance_m):.2f}m"
                if obstacle_distance_m is not None
                else "Range stream healthy"
            )
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.PASS,
                message=message,
            )
        detail = self._topic_diagnostic_message("raw_lidar")
        return CheckResult(
            name="Warehouse LiDAR",
            status=CheckStatus.FAIL,
            message=detail or "LiDAR/range health is unknown; raw_lidar topic not publishing",
        )

    def check_scan_layers(self) -> CheckResult:
        layers = list(getattr(self.mission, "scan_layers", []) or [])
        if not layers:
            return CheckResult(
                name="Warehouse Scan Layers",
                status=CheckStatus.FAIL,
                message="No scan layers were generated",
            )
        top_z = max(float(layer.z_m) for layer in layers)
        ceiling_height = getattr(self.mission, "ceiling_height_m", None)
        ceiling_margin = float(getattr(self.mission, "ceiling_margin_m", 0.0))
        if ceiling_height is not None and top_z + ceiling_margin > float(ceiling_height):
            return CheckResult(
                name="Warehouse Scan Layers",
                status=CheckStatus.FAIL,
                message=(
                    f"Top scan layer {top_z:.2f}m plus margin {ceiling_margin:.2f}m "
                    f"exceeds ceiling {float(ceiling_height):.2f}m"
                ),
            )
        ceiling_distance = getattr(self.v, "ceiling_distance_m", None)
        if ceiling_distance is not None and float(ceiling_distance) < ceiling_margin:
            return CheckResult(
                name="Warehouse Scan Layers",
                status=CheckStatus.FAIL,
                message=(
                    f"Measured ceiling distance {float(ceiling_distance):.2f}m is below "
                    f"required margin {ceiling_margin:.2f}m"
                ),
            )
        return CheckResult(
            name="Warehouse Scan Layers",
            status=CheckStatus.PASS,
            message=f"{len(layers)} layers, top altitude {top_z:.2f}m",
        )

    def check_corridor_geometry(self) -> CheckResult:
        corridors = list(getattr(self.mission, "corridors", []) or [])
        if not corridors:
            return CheckResult(
                name="Warehouse Corridors",
                status=CheckStatus.FAIL,
                message="No warehouse corridors were generated",
            )
        clearance_m = float(getattr(self.mission, "clearance_m", 0.6))
        narrow = []
        short = []
        for corridor in corridors:
            start = corridor.start
            end = corridor.end
            length_m = math.hypot(end.x_m - start.x_m, end.y_m - start.y_m)
            if float(corridor.width_m) < clearance_m * 2.0:
                narrow.append(corridor.corridor_id)
            if length_m < clearance_m * 2.0:
                short.append(corridor.corridor_id)
        if narrow:
            return CheckResult(
                name="Warehouse Corridors",
                status=CheckStatus.FAIL,
                message=f"Corridors too narrow for clearance: {', '.join(narrow[:5])}",
            )
        if short:
            return CheckResult(
                name="Warehouse Corridors",
                status=CheckStatus.FAIL,
                message=f"Corridors too short for stable scan passes: {', '.join(short[:5])}",
            )
        return CheckResult(
            name="Warehouse Corridors",
            status=CheckStatus.PASS,
            message=f"{len(corridors)} corridors satisfy clearance and length checks",
        )

    def check_keepout_conflicts(self) -> CheckResult:
        keepouts = list(getattr(self.mission, "keepout_zones", []) or [])
        obstacles = list(getattr(self.mission, "obstacles_3d", []) or [])
        corridors = list(getattr(self.mission, "corridors", []) or [])
        clearance_m = float(getattr(self.mission, "clearance_m", 0.6))

        if not keepouts and not obstacles:
            return CheckResult(
                name="Warehouse Keepouts",
                status=CheckStatus.PASS,
                message="No keepout or obstacle conflicts were declared",
            )

        corridor_geoms = [
            LineString(
                [
                    (float(c.start.x_m), float(c.start.y_m)),
                    (float(c.end.x_m), float(c.end.y_m)),
                ]
            ).buffer(clearance_m)
            for c in corridors
        ]
        for zone in keepouts:
            zone_poly = Polygon([(pt.x_m, pt.y_m) for pt in zone.footprint])
            for geom in corridor_geoms:
                if geom.intersects(zone_poly):
                    return CheckResult(
                        name="Warehouse Keepouts",
                        status=CheckStatus.FAIL,
                        message=f"Corridor path intersects keepout zone '{zone.zone_id}'",
                    )
        for obstacle in obstacles:
            half_x = float(obstacle.size_x_m) / 2.0
            half_y = float(obstacle.size_y_m) / 2.0
            obstacle_poly = Point(
                float(obstacle.center.x_m),
                float(obstacle.center.y_m),
            ).buffer(max(half_x, half_y), cap_style=3)
            for geom in corridor_geoms:
                if geom.intersects(obstacle_poly):
                    return CheckResult(
                        name="Warehouse Keepouts",
                        status=CheckStatus.FAIL,
                        message=f"Corridor path intersects obstacle '{obstacle.obstacle_id}'",
                    )
        return CheckResult(
            name="Warehouse Keepouts",
            status=CheckStatus.PASS,
            message="Corridors clear all declared keepouts and obstacles",
        )

    async def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        results.append(self.check_waypoint_count_limit())
        results.append(self.check_speed_limits())
        results.append(self.check_local_origin())
        results.append(self.check_local_position_lock())
        results.append(self.check_ros_bridge())
        results.append(self.check_ros_graph())
        results.append(self.check_camera_topics())
        results.append(self.check_stereo_sync())
        results.append(self.check_imu_topic())
        results.append(self.check_tf_tree())
        results.append(self.check_visual_slam())
        results.append(self.check_nvblox())
        results.append(self.check_mapping_disk())
        results.append(self.check_sensor_rig())
        results.append(self.check_battery_margin())
        results.append(self.check_dock_marker())
        results.append(self.check_odometry_health())
        results.append(self.check_lidar_health())
        results.append(self.check_scan_layers())
        results.append(self.check_corridor_geometry())
        results.append(self.check_keepout_conflicts())
        return results


class IndoorExplorationMissionPreflight(MissionPreflightBase):
    """Mission-parameter checks for indoor frontier exploration."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: IndoorExplorationMission = context.mission

    def check_mission_parameters(self) -> CheckResult:
        if float(self.mission.max_mission_time_s) <= 0:
            return CheckResult(
                name="Indoor Mission Parameters",
                status=CheckStatus.FAIL,
                message="max_mission_time_s must be positive",
            )
        if float(self.mission.max_exploration_radius_m) <= float(
            self.mission.safe_takeoff_bubble_radius_m
        ):
            return CheckResult(
                name="Indoor Mission Parameters",
                status=CheckStatus.FAIL,
                message="max_exploration_radius_m must exceed the dock takeoff bubble",
            )
        if float(self.mission.max_path_length_m) <= float(self.mission.max_exploration_radius_m):
            return CheckResult(
                name="Indoor Mission Parameters",
                status=CheckStatus.FAIL,
                message="max_path_length_m must exceed max_exploration_radius_m",
            )
        if float(self.mission.occupancy_resolution_m) > float(
            self.mission.minimum_corridor_clearance_m
        ):
            return CheckResult(
                name="Indoor Mission Parameters",
                status=CheckStatus.FAIL,
                message="occupancy_resolution_m is too coarse for the corridor clearance constraint",
            )
        return CheckResult(
            name="Indoor Mission Parameters",
            status=CheckStatus.PASS,
            message="Indoor exploration limits are internally consistent",
        )

    def check_frame_config(self) -> CheckResult:
        dock = self.mission.dock
        frames = {
            dock.pose.frame_id,
            dock.entry_pose.frame_id,
            dock.exit_pose.frame_id,
            getattr(self.mission, "local_control_mode", "local_setpoint"),
        }
        if (
            dock.pose.frame_id != "map"
            or dock.entry_pose.frame_id != "map"
            or dock.exit_pose.frame_id != "map"
        ):
            return CheckResult(
                name="Indoor Frames",
                status=CheckStatus.FAIL,
                message="Dock, entry, and exit poses must be declared in the map frame",
            )
        if "local_setpoint" not in frames:
            return CheckResult(
                name="Indoor Frames",
                status=CheckStatus.FAIL,
                message="Indoor exploration requires local_setpoint control mode",
            )
        return CheckResult(
            name="Indoor Frames",
            status=CheckStatus.PASS,
            message="Dock, map, and local-control frames are configured",
        )

    def check_dock_geometry(self) -> CheckResult:
        dock = self.mission.dock
        entry_distance = math.hypot(
            float(dock.entry_pose.x_m) - float(dock.pose.x_m),
            float(dock.entry_pose.y_m) - float(dock.pose.y_m),
        )
        exit_distance = math.hypot(
            float(dock.exit_pose.x_m) - float(dock.pose.x_m),
            float(dock.exit_pose.y_m) - float(dock.pose.y_m),
        )
        if entry_distance > float(self.mission.dock_search_radius_m) * 4.0:
            return CheckResult(
                name="Indoor Dock Geometry",
                status=CheckStatus.FAIL,
                message="Dock entry pose is too far from the dock anchor",
            )
        if exit_distance > float(self.mission.max_exploration_radius_m):
            return CheckResult(
                name="Indoor Dock Geometry",
                status=CheckStatus.FAIL,
                message="Dock exit pose exceeds the maximum exploration radius",
            )
        return CheckResult(
            name="Indoor Dock Geometry",
            status=CheckStatus.PASS,
            message=(f"Dock entry {entry_distance:.1f}m, exit {exit_distance:.1f}m from dock"),
        )

    def check_return_reserve(self) -> CheckResult:
        if float(self.mission.battery_return_reserve_pct) <= float(
            self.mission.battery_emergency_land_reserve_pct
        ):
            return CheckResult(
                name="Indoor Return Reserve",
                status=CheckStatus.FAIL,
                message="Return reserve must exceed emergency land reserve",
            )
        return CheckResult(
            name="Indoor Return Reserve",
            status=CheckStatus.PASS,
            message=(
                f"Return reserve {float(self.mission.battery_return_reserve_pct):.1f}% > "
                f"emergency reserve {float(self.mission.battery_emergency_land_reserve_pct):.1f}%"
            ),
        )

    def check_localization_thresholds(self) -> CheckResult:
        if float(self.mission.localization_confidence_return_threshold) > float(
            self.mission.localization_confidence_min
        ):
            return CheckResult(
                name="Indoor Localization Thresholds",
                status=CheckStatus.FAIL,
                message="Return threshold must not exceed the continue-flight confidence threshold",
            )
        return CheckResult(
            name="Indoor Localization Thresholds",
            status=CheckStatus.PASS,
            message=(
                f"continue={float(self.mission.localization_confidence_min):.2f}, "
                f"return={float(self.mission.localization_confidence_return_threshold):.2f}"
            ),
        )

    async def run(self) -> list[CheckResult]:
        return [
            self.check_speed_limits(),
            self.check_mission_parameters(),
            self.check_frame_config(),
            self.check_dock_geometry(),
            self.check_return_reserve(),
            self.check_localization_thresholds(),
        ]


def create_mission_preflight(context: PreflightContext) -> MissionPreflightBase:
    mission_type = str(getattr(context.mission, "type", "") or "").lower()

    aliases = {
        "survey": "grid",
        "circle": "orbit",
        "poi": "orbit",
        "private_patrol": "perimeter_patrol",
        "polygon": "perimeter_patrol",
        "patrol": "perimeter_patrol",
    }

    mission_type = aliases.get(mission_type, mission_type)

    mission_classes: dict[str, type[MissionPreflightBase]] = {
        "grid": GridMissionPreflight,
        "warehouse_scan": WarehouseScanMissionPreflight,
        "indoor_exploration": IndoorExplorationMissionPreflight,
        "terrain_follow": TerrainFollowMissionPreflight,
        "orbit": OrbitMissionPreflight,
        "perimeter_patrol": PerimeterPatrolMissionPreflight,
        "adaptive_altitude": AdaptiveAltitudeMissionPreflight,
        "route": WaypointMissionPreflight,
    }

    return mission_classes.get(mission_type, WaypointMissionPreflight)(context)
