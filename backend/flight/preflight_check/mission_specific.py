from .schemas import CheckResult, CheckStatus
from math import tan, radians, atan, sqrt, pi, sin, cos
from typing import List, Optional, Any, Dict, Iterable, Tuple, Sequence
from ..missions.schemas import (
    Mission, GridMission, OrbitMission, TerrainFollowMission,
    PerimeterPatrolMission, AdaptiveAltitudeMission, Waypoint
)
from .preflight_context import PreflightContext
import math
from backend.drone.models import Coordinate
from backend.analysis.range_estimator import SimpleWhPerKmModel, RangeEstimateResult



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

def create_mission_preflight(context: PreflightContext) -> MissionPreflightBase:

    mission_type = context.mission.type.lower() if hasattr(context.mission, 'type') else ""

    mission_classes = {
        'grid': GridMissionPreflight,
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
