from __future__ import annotations

import math
from typing import Any

from backend.core.config.runtime import env_truthy, settings

from ..context import PreflightContext
from ..schemas import CheckResult, CheckStatus
from backend.modules.preflight.range_estimator import SimpleWhPerKmModel


def warehouse_sim_mode() -> bool:
    if env_truthy(settings.sim_mode) or env_truthy(settings.indoor_nav):
        return True
    if env_truthy(settings.warehouse_sim_mode) or env_truthy(settings.warehouse_gazebo_sim):
        return True
    return False


_warehouse_sim_mode = warehouse_sim_mode


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

    async def _run_independent_checks(self, *checks: Any) -> list[CheckResult]:
        """Run deterministic read-only checks concurrently, preserving order."""
        # Context caches update hit/miss counters. Only a precomputed immutable
        # snapshot is safe to share across worker threads; otherwise retain the
        # deterministic sequential path.
        if self.ctx.precomputed is not None:
            outputs = await asyncio.gather(*(asyncio.to_thread(check) for check in checks))
        else:
            outputs = [check() for check in checks]
        results: list[CheckResult] = []
        for output in outputs:
            results.extend(output if isinstance(output, list) else [output])
        return results

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

        if bool(self.ctx.get_threshold("GEOFENCE_CONTAINMENT_ANCHOR_ONLY", False)):
            pts = [pts[0]]

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


