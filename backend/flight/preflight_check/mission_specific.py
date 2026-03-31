from .schemas import CheckResult, CheckStatus
from math import tan, radians, atan, sqrt, pi, sin, cos
from typing import List, Optional, Any, Dict, Iterable, Tuple, Sequence
from ..missions.schemas import (
    Mission, GridMission, OrbitMission, TerrainFollowMission,
    PerimeterPatrolMission, AdaptiveAltitudeMission, Waypoint,
    WarehouseScanMission, IndoorExplorationMission,
)
from .preflight_context import PreflightContext
import math
from backend.drone.models import Coordinate
from backend.analysis.range_estimator import SimpleWhPerKmModel, RangeEstimateResult
from shapely.geometry import LineString, Point, Polygon



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
        self.A_LAT_MAX = context.get_threshold('A_LAT_MAX', 9.81)
        self.BANK_MAX_DEG = context.get_threshold('BANK_MAX_DEG', 35)
        self.TURN_PENALTY_S = context.get_threshold('TURN_PENALTY_S', 5)
        self.AGL_MIN = context.get_threshold('AGL_MIN', 10)
        self.AGL_MAX = context.get_threshold('AGL_MAX', 120)

    def _get_distance(self, idx1: int, idx2: int) -> float:
        """Get cached distance between waypoints."""
        return self.ctx.get_distance(idx1, idx2)

    def _get_terrain(self, idx: int) -> Optional[float]:
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

    def _as_latlon(self, p: Any) -> Optional[Tuple[float, float]]:
        """Best-effort extraction of (lat, lon) from waypoint/polygon point."""
        try:
            if isinstance(p, (tuple, list)) and len(p) >= 2:
                return float(p[0]), float(p[1])
            if isinstance(p, dict) and "lat" in p and "lon" in p:
                return float(p["lat"]), float(p["lon"])
            if hasattr(p, "lat") and hasattr(p, "lon"):
                return float(getattr(p, "lat")), float(getattr(p, "lon"))
            if hasattr(p, "latitude") and hasattr(p, "longitude"):
                return float(getattr(p, "latitude")), float(getattr(p, "longitude"))
        except Exception:
            return None
        return None

    def _normalize_polygon(self, poly: Iterable[Any]) -> List[Tuple[float, float]]:
        pts: List[Tuple[float, float]] = []
        for p in poly:
            ll = self._as_latlon(p)
            if ll is not None:
                pts.append(ll)
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts.pop()
        return pts

    @staticmethod
    def _point_in_polygon(lat: float, lon: float, polygon: Sequence[Tuple[float, float]]) -> bool:
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

    def _mission_points(self) -> List[Tuple[float, float]]:
        """Representative mission points for containment/range checks."""
        pts: List[Tuple[float, float]] = []
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
            return CheckResult(name="Mission Speed", status=CheckStatus.SKIP, message="No mission speed provided")

        v_cmd = float(self.mission.speed)
        v_max = getattr(self.v, "speed_max_mps", None)
        v_cruise = getattr(self.v, "cruise_speed_mps", None)

        if v_max is not None and v_cmd > float(v_max):
            return CheckResult(name="Mission Speed", status=CheckStatus.FAIL, message=f"{v_cmd:.1f}m/s > max {float(v_max):.1f}m/s")

        if v_cruise is not None and v_cmd < 0.3 * float(v_cruise):
            return CheckResult(name="Mission Speed", status=CheckStatus.WARN, message=f"{v_cmd:.1f}m/s unusually low vs cruise {float(v_cruise):.1f}m/s")

        return CheckResult(name="Mission Speed", status=CheckStatus.PASS, message=f"{v_cmd:.1f} m/s")

    def check_waypoint_count_limit(self) -> CheckResult:
        """Guard against FC mission-item limits / upload issues."""
        wps = getattr(self.mission, "waypoints", None)
        if not wps:
            return CheckResult(name="Waypoint Count", status=CheckStatus.SKIP, message="No waypoints")
        max_wps = int(self._thr("MAX_WAYPOINTS", 700))
        if len(wps) > max_wps:
            return CheckResult(name="Waypoint Count", status=CheckStatus.FAIL, message=f"{len(wps)} > {max_wps}")
        return CheckResult(name="Waypoint Count", status=CheckStatus.PASS, message=f"{len(wps)}")

    def check_agl_envelope_basic(self) -> CheckResult:
        """For missions with altitude_agl, enforce envelope."""
        agl = getattr(self.mission, "altitude_agl", None)
        if agl is None:
            return CheckResult(name="AGL Envelope", status=CheckStatus.SKIP, message="No altitude_agl on mission")
        if float(agl) < float(self.AGL_MIN):
            return CheckResult(name="AGL Envelope", status=CheckStatus.FAIL, message=f"AGL {agl}m < min {self.AGL_MIN}m")
        if float(agl) > float(self.AGL_MAX):
            return CheckResult(name="AGL Envelope", status=CheckStatus.FAIL, message=f"AGL {agl}m > max {self.AGL_MAX}m")
        return CheckResult(name="AGL Envelope", status=CheckStatus.PASS, message=f"AGL {agl}m")

    def check_max_range_from_home(self) -> CheckResult:
        """Ensure mission remains within a max radius from home (if home known)."""
        pts = self._mission_points()
        if not pts:
            return CheckResult(name="Max Range From Home", status=CheckStatus.SKIP, message="No mission points")

        home_lat = getattr(self.v, "home_lat", None)
        home_lon = getattr(self.v, "home_lon", None)
        if home_lat is None or home_lon is None:
            return CheckResult(name="Max Range From Home", status=CheckStatus.SKIP, message="Home location not available")

        max_range_m = float(self._thr("MAX_RANGE_M", 5000.0))
        worst = 0.0
        for (lat, lon) in pts:
            d_m = self._haversine_m(float(home_lat), float(home_lon), lat, lon)
            worst = max(worst, d_m)

        if worst > max_range_m:
            enforce = bool(self._thr("ENFORCE_PREFLIGHT_RANGE", True))
            status = CheckStatus.FAIL if enforce else CheckStatus.WARN
            detail = "" if enforce else " (enforcement disabled)"
            return CheckResult(
                name="Max Range From Home",
                status=status,
                message=f"{worst:.0f}m > {max_range_m:.0f}m{detail}"
            )
        return CheckResult(name="Max Range From Home", status=CheckStatus.PASS, message=f"{worst:.0f}m")

    def check_geofence_containment(self) -> CheckResult:
        """Validate mission points are inside ctx.geofence_polygon (if provided)."""
        raw_poly = getattr(self.ctx, "geofence_polygon", None)
        if not raw_poly:
            return CheckResult(name="Geofence Containment", status=CheckStatus.SKIP, message="No geofence polygon")
        poly = self._normalize_polygon(raw_poly)
        if len(poly) < 3:
            return CheckResult(name="Geofence Containment", status=CheckStatus.FAIL, message="Invalid geofence polygon")

        pts = self._mission_points()
        if not pts:
            return CheckResult(name="Geofence Containment", status=CheckStatus.SKIP, message="No mission points")

        for i, (lat, lon) in enumerate(pts):
            if not self._point_in_polygon(lat, lon, poly):
                return CheckResult(name="Geofence Containment", status=CheckStatus.FAIL, message=f"Point {i} outside geofence")
        return CheckResult(name="Geofence Containment", status=CheckStatus.PASS, message="All mission points inside")

    def check_no_fly_zones(self) -> CheckResult:
        """Validate mission points are not inside NFZ buffers (if ctx implements it)."""
        nfz = getattr(self.ctx, "no_fly_zones", None)
        if not nfz:
            return CheckResult(name="No-Fly Zones", status=CheckStatus.SKIP, message="No NFZ data")
        if not hasattr(self.ctx, "check_no_fly_zones"):
            return CheckResult(name="No-Fly Zones", status=CheckStatus.WARN, message="NFZ present but ctx.check_no_fly_zones not implemented")

        buffer_m = float(self.ctx.get_threshold("NFZ_BUFFER_M", 50.0))
        pts = self._mission_points()
        if not pts:
            return CheckResult(name="No-Fly Zones", status=CheckStatus.SKIP, message="No mission points")

        for i, (lat, lon) in enumerate(pts):
            if not self.ctx.check_no_fly_zones(lat, lon, buffer_m):
                return CheckResult(name="No-Fly Zones", status=CheckStatus.FAIL, message=f"Point {i} inside/near NFZ (buffer {buffer_m:.0f}m)")
        return CheckResult(name="No-Fly Zones", status=CheckStatus.PASS, message=f"Buffer {buffer_m:.0f}m OK")

    def check_basic_terrain_clearance(self) -> CheckResult:
        """Generic clearance check using cached waypoint terrain (if available)."""
        wps = getattr(self.mission, "waypoints", None)
        if not wps:
            return CheckResult(name="Terrain Clearance", status=CheckStatus.SKIP, message="No waypoints")
        if not hasattr(self.ctx, "get_waypoint_terrain"):
            return CheckResult(name="Terrain Clearance", status=CheckStatus.SKIP, message="No cached terrain in context")

        min_clearance = float(self.ctx.get_threshold("MIN_CLEARANCE_M", 5.0))
        for i, wp in enumerate(wps):
            terrain = self._get_terrain(i)
            if terrain is None:
                return CheckResult(name="Terrain Clearance", status=CheckStatus.WARN, message=f"Terrain missing at waypoint {i}")
            alt = getattr(wp, "alt", None)
            if alt is None:
                return CheckResult(name="Terrain Clearance", status=CheckStatus.WARN, message=f"Waypoint {i} missing alt")
            clearance = float(alt) - float(terrain)
            if clearance < min_clearance:
                return CheckResult(name="Terrain Clearance", status=CheckStatus.FAIL, message=f"WP{i} clearance {clearance:.1f}m < {min_clearance:.1f}m")
        return CheckResult(name="Terrain Clearance", status=CheckStatus.PASS, message=f"Min clearance >= {min_clearance:.1f}m")

    def check_grid_turn_margin(self) -> CheckResult:
        """Grid missions: approximate row-end turning feasibility based on spacing and speed."""
        if not hasattr(self.mission, "speed") or self.mission.speed is None:
            return CheckResult(name="Grid Turn Margin", status=CheckStatus.SKIP, message="No mission speed")
        spacing = getattr(self.mission, "line_spacing_m", None)
        if spacing is None:
            return CheckResult(name="Grid Turn Margin", status=CheckStatus.SKIP, message="No line_spacing_m")

        v = float(self.mission.speed)
        bank_max = float(self.BANK_MAX_DEG)
        g = 9.81
        # min radius from bank angle limit
        min_r = v * v / (g * math.tan(math.radians(bank_max)) + 1e-9)
        # crude available radius ~ half spacing (U-turn in corridor)
        avail_r = 0.5 * float(spacing)

        if avail_r <= 0:
            return CheckResult(name="Grid Turn Margin", status=CheckStatus.SKIP, message="Invalid spacing")

        if avail_r < 0.8 * min_r:
            return CheckResult(name="Grid Turn Margin", status=CheckStatus.FAIL, message=f"Avail R~{avail_r:.1f}m < min {min_r:.1f}m (bank {bank_max:.0f}°)")
        if avail_r < min_r:
            return CheckResult(name="Grid Turn Margin", status=CheckStatus.WARN, message=f"Avail R~{avail_r:.1f}m slightly < min {min_r:.1f}m")
        return CheckResult(name="Grid Turn Margin", status=CheckStatus.PASS, message=f"Avail R~{avail_r:.1f}m, min {min_r:.1f}m")


    def check_preflight_range(self) -> CheckResult:
        """Range check over the full clicked route."""
        from backend.config import settings

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

        v_kmh = max(0.1, settings.cruise_speed_mps * 3.6)
        wh_per_km = settings.cruise_power_w / v_kmh
        required_Wh = distance_km * wh_per_km
        available_Wh = (
            None
            if level_frac is None
            else max(
                0.0,
                settings.battery_capacity_wh
                * max(0.0, level_frac - settings.energy_reserve_frac),
                )
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


    async def run(self) -> List[CheckResult]:
        return [CheckResult(name="Mission Type", status=CheckStatus.WARN, message="No mission-specific checks registered")]


class WaypointMissionPreflight(MissionPreflightBase):
    """Generic waypoint-route mission (non-grid/orbit/patrol) checks."""

    async def run(self) -> List[CheckResult]:
        results: List[CheckResult] = []
        results.append(self.check_waypoint_count_limit())
        results.append(self.check_speed_limits())
        results.append(self.check_max_range_from_home())
        results.append(self.check_geofence_containment())
        results.append(self.check_no_fly_zones())
        results.append(self.check_basic_terrain_clearance())
        results.append(self.check_preflight_range()) #check parameters
        return results


class GridMissionPreflight(MissionPreflightBase):
    """Grid/Survey mission preflight checks."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        # Type cast for IDE support
        self.mission: GridMission = context.mission

    def check_camera_footprint(self) -> CheckResult:
        """Check if line spacing is compatible with camera footprint."""
        if not hasattr(self.mission, 'camera') or not self.mission.camera:
            return CheckResult(
                name="Grid Camera Footprint",
                status=CheckStatus.SKIP,
                message="No camera specifications provided"
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
                message="; ".join(issues)
            )

        return CheckResult(
            name="Grid Camera Footprint",
            status=CheckStatus.PASS,
            message=f"Footprint: {footprint_width_m:.1f}×{footprint_height_m:.1f}m"
        )

    def check_mission_duration(self) -> CheckResult:
        """Check if mission duration is within vehicle limits."""
        total_distance = self.ctx.total_distance()
        flight_time_s = total_distance / self.mission.speed if self.mission.speed > 0 else 0

        # Add turn penalties
        if hasattr(self.mission, 'grid_segments') and self.mission.grid_segments:
            num_turns = len(self.mission.grid_segments) - 1
            flight_time_s += self.TURN_PENALTY_S * num_turns

        if hasattr(self.v, 'max_flight_time_s') and self.v.max_flight_time_s:
            if flight_time_s > self.v.max_flight_time_s:
                return CheckResult(
                    name="Grid Duration",
                    status=CheckStatus.FAIL,
                    message=f"Est. time {flight_time_s/60:.1f}min > "
                            f"max {self.v.max_flight_time_s/60:.1f}min"
                )

        return CheckResult(
            name="Grid Duration",
            status=CheckStatus.PASS,
            message=f"Est. time: {flight_time_s/60:.1f}min"
        )

    async def run(self) -> List[CheckResult]:
        """Run all grid mission checks."""
        results: List[CheckResult] = []
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

    def check_terrain_follow_feasibility(self) -> List[CheckResult]:
        """Check if terrain following is feasible."""
        results = []

        if len(self.mission.waypoints) < 2:
            return [CheckResult(
                name="Terrain Follow",
                status=CheckStatus.FAIL,
                message="Insufficient waypoints"
            )]

        max_climb_rate = 0
        max_descent_rate = 0

        for i in range(1, len(self.mission.waypoints)):
            # Get terrain from context (cached)
            current_terrain = self._get_terrain(i) or 0
            prev_terrain = self._get_terrain(i-1) or 0

            # Get distance from context (cached)
            segment_distance = self._get_distance(i-1, i)
            segment_time = segment_distance / self.mission.speed if self.mission.speed > 0 else 0

            if segment_time > 0:
                alt_change = (current_terrain - prev_terrain) + self.mission.min_agl
                rate = alt_change / segment_time

                if rate > 0:
                    max_climb_rate = max(max_climb_rate, rate)
                else:
                    max_descent_rate = max(max_descent_rate, abs(rate))

        # Check against vehicle limits
        climb_rate_max = getattr(self.v, 'climb_rate_max', 5)
        if max_climb_rate > climb_rate_max:
            results.append(CheckResult(
                name="Climb Rate",
                status=CheckStatus.FAIL,
                message=f"Required climb {max_climb_rate:.1f}m/s > max {climb_rate_max}m/s"
            ))
        else:
            results.append(CheckResult(
                name="Climb Rate",
                status=CheckStatus.PASS,
                message=f"Max climb: {max_climb_rate:.1f}m/s"
            ))

        descent_rate_max = getattr(self.v, 'descent_rate_max', 3)
        if max_descent_rate > descent_rate_max:
            results.append(CheckResult(
                name="Descent Rate",
                status=CheckStatus.FAIL,
                message=f"Required descent {max_descent_rate:.1f}m/s > max {descent_rate_max}m/s"
            ))
        else:
            results.append(CheckResult(
                name="Descent Rate",
                status=CheckStatus.PASS,
                message=f"Max descent: {max_descent_rate:.1f}m/s"
            ))

        return results

    async def run(self) -> List[CheckResult]:
        """Run all terrain-following mission checks."""
        results: List[CheckResult] = []
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

    def check_turn_feasibility(self) -> List[CheckResult]:
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
            results.append(CheckResult(
                name="Orbit Bank Angle",
                status=CheckStatus.PASS,
                message=f"Bank: {bank_deg:.1f}° (max {self.BANK_MAX_DEG}°)"
            ))
        else:
            results.append(CheckResult(
                name="Orbit Bank Angle",
                status=CheckStatus.FAIL,
                message=f"Bank angle {bank_deg:.1f}° > {self.BANK_MAX_DEG}°"
            ))

        # Lateral acceleration check
        if a_lat <= self.A_LAT_MAX:
            results.append(CheckResult(
                name="Orbit Lateral Acceleration",
                status=CheckStatus.PASS,
                message=f"Lateral accel: {a_lat:.2f}m/s² (max {self.A_LAT_MAX}m/s²)"
            ))
        else:
            results.append(CheckResult(
                name="Orbit Lateral Acceleration",
                status=CheckStatus.FAIL,
                message=f"Lateral accel {a_lat:.2f}m/s² > {self.A_LAT_MAX}m/s²"
            ))

        return results

    def check_clearance(self) -> CheckResult:
        """Check clearance around POI."""
        # Check minimum standoff
        if self.mission.radius < self.mission.min_standoff_m:
            return CheckResult(
                name="POI Clearance",
                status=CheckStatus.FAIL,
                message=f"Orbit radius {self.mission.radius}m < min standoff {self.mission.min_standoff_m}m"
            )

        # Check AGL if POI location has terrain
        if self.mission.poi_location:
            agl = self.mission.altitude_agl
            if agl < self.AGL_MIN or agl > self.AGL_MAX:
                return CheckResult(
                    name="Orbit AGL",
                    status=CheckStatus.WARN,
                    message=f"Orbit AGL {agl}m may be outside safe envelope ({self.AGL_MIN}-{self.AGL_MAX}m)"
                )

        return CheckResult(
            name="POI Clearance",
            status=CheckStatus.PASS,
            message=f"Radius: {self.mission.radius}m, Standoff OK"
        )

    async def run(self) -> List[CheckResult]:
        """Run all orbit mission checks."""
        results: List[CheckResult] = []
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
                message=f"Polygon has {len(self.mission.polygon)} points, need at least 3"
            )

        # Polygon is already validated by Pydantic
        return CheckResult(
            name="Polygon Validity",
            status=CheckStatus.PASS,
            message=f"Polygon valid with {len(self.mission.polygon)} points"
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
        if not hasattr(self.mission, 'polygon') or len(self.mission.polygon) < 3:
            return CheckResult(
                name="Cornering Limits",
                status=CheckStatus.SKIP,
                message="Insufficient polygon data"
            )

        v = getattr(self.mission, 'speed', getattr(self.v, 'cruise_speed_mps', 10))
        max_turn_rate = getattr(self.v, 'max_turn_rate_rad_s', 0.5)

        # Calculate minimum turn radius from max turn rate
        # turn_rate = v / r  => r_min = v / max_turn_rate
        r_min = v / max_turn_rate if max_turn_rate > 0 else float('inf')

        # Also check against max lateral acceleration
        a_lat_max = getattr(self, 'A_LAT_MAX', 9.81)
        r_min_accel = v**2 / a_lat_max
        r_min = max(r_min, r_min_accel)

        # Check each corner
        tight_corners = []
        polygon = self.mission.polygon

        # Use all corners (including closing the loop)
        for i in range(len(polygon)):
            p1 = polygon[i]
            p2 = polygon[(i+1) % len(polygon)]
            p3 = polygon[(i+2) % len(polygon)]

            # Calculate turn angle at p2
            turn_angle = self._calculate_turn_angle(p1, p2, p3)

            # Skip if nearly straight (angle close to 0 or π)
            if turn_angle < 0.05 or turn_angle > math.pi - 0.05:
                continue

            # Calculate chord length (distance from p2 to p3)
            p2 = polygon[(i+1) % len(polygon)]
            p3 = polygon[(i+2) % len(polygon)]
            chord_length = self.ctx.get_distance_between_points(p2, p3)

            # For a given turn angle, the required radius can be estimated
            if turn_angle > 0:
                # Required radius to make this turn at current speed
                required_radius = chord_length / (2 * math.sin(turn_angle/2))

                if required_radius < r_min:
                    tight_corners.append({
                        'corner': i,
                        'turn_angle_deg': math.degrees(turn_angle),
                        'required_radius': required_radius,
                        'chord_length': chord_length
                    })

        if tight_corners:
            # Sort by most severe
            tight_corners.sort(key=lambda x: x['required_radius'])
            worst = tight_corners[0]

            message = (f"{len(tight_corners)} corners exceed turn limits. "
                       f"Worst: corner {worst['corner']} requires {worst['required_radius']:.1f}m radius "
                       f"(min {r_min:.1f}m), turn angle {worst['turn_angle_deg']:.1f}°")

            return CheckResult(
                name="Cornering Limits",
                status=CheckStatus.FAIL,
                message=message
            )

        return CheckResult(
            name="Cornering Limits",
            status=CheckStatus.PASS,
            message=f"All corners within turn limits (min radius {r_min:.1f}m)"
        )

    def check_boundary_buffer(self) -> CheckResult:
        """Check if path maintains safe buffer from boundary."""
        if self.mission.path_offset_m < self.mission.boundary_buffer_min:
            return CheckResult(
                name="Boundary Buffer",
                status=CheckStatus.FAIL,
                message=f"Path offset {self.mission.path_offset_m}m < min buffer {self.mission.boundary_buffer_min}m"
            )

        return CheckResult(
            name="Boundary Buffer",
            status=CheckStatus.PASS,
            message=f"Buffer: {self.mission.path_offset_m}m (min {self.mission.boundary_buffer_min}m)"
        )

    async def run(self) -> List[CheckResult]:
        """Run all perimeter patrol checks."""
        results: List[CheckResult] = []
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

    def check_altitude_limits(self) -> List[CheckResult]:
        """Check if commanded altitudes are within limits."""
        results = []

        for i, wp in enumerate(self.mission.waypoints):
            terrain = self._get_terrain(i) or 0
            cmd_alt = terrain + self.mission.target_agl

            if cmd_alt > self.mission.alt_ceiling_msl:
                results.append(CheckResult(
                    name=f"Waypoint {i} Altitude",
                    status=CheckStatus.FAIL,
                    message=f"Altitude {cmd_alt}m > ceiling {self.mission.alt_ceiling_msl}m"
                ))
            elif cmd_alt < self.mission.alt_floor_msl:
                results.append(CheckResult(
                    name=f"Waypoint {i} Altitude",
                    status=CheckStatus.FAIL,
                    message=f"Altitude {cmd_alt}m < floor {self.mission.alt_floor_msl}m"
                ))

        if not results:
            results.append(CheckResult(
                name="Altitude Limits",
                status=CheckStatus.PASS,
                message="All altitudes within limits"
            ))

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
                        message=f"Waypoint {i} AGL {agl:.1f}m outside envelope [{self.mission.agl_min}, {self.mission.agl_max}]m"
                    )

        return CheckResult(
            name="AGL Envelope",
            status=CheckStatus.PASS,
            message=f"Target AGL {self.mission.target_agl}m within envelope"
        )

    async def run(self) -> List[CheckResult]:
        """Run all adaptive altitude checks."""
        results: List[CheckResult] = []
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
            detail = (
                f"Drift {float(drift_m):.2f}m"
                if drift_m is not None
                else "Odometry healthy"
            )
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
        lidar_healthy = getattr(self.v, "lidar_healthy", None)
        obstacle_distance_m = getattr(self.v, "obstacle_distance_m", None)
        clearance_m = float(getattr(self.mission, "clearance_m", 0.6))
        if lidar_healthy is False:
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.FAIL,
                message="LiDAR/range input is unhealthy",
            )
        if (
            obstacle_distance_m is not None
            and float(obstacle_distance_m) < clearance_m
        ):
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
        return CheckResult(
            name="Warehouse LiDAR",
            status=CheckStatus.WARN,
            message="LiDAR/range health is unknown from current telemetry",
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

    async def run(self) -> List[CheckResult]:
        results: List[CheckResult] = []
        results.append(self.check_waypoint_count_limit())
        results.append(self.check_speed_limits())
        results.append(self.check_local_origin())
        results.append(self.check_local_position_lock())
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
        if float(self.mission.max_exploration_radius_m) <= float(self.mission.safe_takeoff_bubble_radius_m):
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
        if float(self.mission.occupancy_resolution_m) > float(self.mission.minimum_corridor_clearance_m):
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
        if dock.pose.frame_id != "map" or dock.entry_pose.frame_id != "map" or dock.exit_pose.frame_id != "map":
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
            message=(
                f"Dock entry {entry_distance:.1f}m, exit {exit_distance:.1f}m from dock"
            ),
        )

    def check_return_reserve(self) -> CheckResult:
        if float(self.mission.battery_return_reserve_pct) <= float(self.mission.battery_emergency_land_reserve_pct):
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
        if float(self.mission.localization_confidence_return_threshold) > float(self.mission.localization_confidence_min):
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

    async def run(self) -> List[CheckResult]:
        return [
            self.check_speed_limits(),
            self.check_mission_parameters(),
            self.check_frame_config(),
            self.check_dock_geometry(),
            self.check_return_reserve(),
            self.check_localization_thresholds(),
        ]

def create_mission_preflight(context: PreflightContext) -> MissionPreflightBase:

    mission_type = context.mission.type.lower() if hasattr(context.mission, 'type') else ""

    mission_classes = {
        'grid': GridMissionPreflight,
        'warehouse_scan': WarehouseScanMissionPreflight,
        'indoor_exploration': IndoorExplorationMissionPreflight,
        'terrain_follow': TerrainFollowMissionPreflight,
        'orbit': OrbitMissionPreflight,
        'perimeter_patrol': PerimeterPatrolMissionPreflight,
        'adaptive_altitude': AdaptiveAltitudeMissionPreflight,
        'route': WaypointMissionPreflight,
    }

    # Handle aliases
    base_type = mission_type
    if mission_type in ['survey']:
        base_type = 'grid'
    elif mission_type in ['circle', 'poi']:
        base_type = 'orbit'
    elif mission_type in ['private_patrol', 'polygon', 'patrol']:
        base_type = 'perimeter_patrol'

    mission_class = mission_classes.get(base_type) or mission_classes.get(mission_type)

    if mission_class:
        return mission_class(context)
    else:
        # Return base class that does nothing
        return MissionPreflightBase(context)
