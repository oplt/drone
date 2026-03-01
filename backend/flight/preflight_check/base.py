from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from .schemas import CheckResult, CheckStatus
from .preflight_context import PreflightContext
from backend.utils.geo import haversine_km


class Priority(IntEnum):
    CRITICAL = 0   # hard gates: link/arming/gps/ekf/battery basics
    SAFETY = 1     # operational safety: fence/nfz/failsafe/terrain
    QUALITY = 2    # quality/health: compass/imu/storage/gnss interference
    INFO = 3       # informational / best-effort diagnostics


@dataclass(frozen=True)
class CheckSpec:
    name: str
    priority: Priority
    is_gate: bool  # if True and FAIL occurs, fail_fast may short-circuit
    coro: Any      # awaitable factory (lambda returning coroutine)


class BasePreflightChecks:
    """
    Baseline preflight checks with:
      - Priority/ordering (critical gates first)
      - Optional fail-fast
      - Real geofence point-in-polygon
      - Common additional checks:
          RC link present, compass health, IMU calibration, arming checks flags,
          storage/logging available, GNSS jamming/interference
    """

    def __init__(self, context: PreflightContext):
        self.ctx = context
        self.v = context.vehicle_state

        # Thresholds (context-overridable)
        self.HDOP_MAX = context.get_threshold("HDOP_MAX", 2.5)
        self.SAT_MIN = context.get_threshold("SAT_MIN", 6)
        self.HOME_MAX_DIST = context.get_threshold("HOME_MAX_DIST", 100.0)  # meters
        self.GPS_FIX_TYPE_MIN = context.get_threshold("GPS_FIX_TYPE_MIN", 3)
        self.EKF_THRESHOLD = context.get_threshold("EKF_THRESHOLD", None)
        self.BATTERY_MIN_V = context.get_threshold("BATTERY_MIN_V", None)

        self.WIND_MAX = context.get_threshold("WIND_MAX", 12.0)  # m/s
        self.GUST_MAX = context.get_threshold("GUST_MAX", 15.0)  # m/s

        self.RTL_MIN_ALT = context.get_threshold("RTL_MIN_ALT", 30.0)  # meters
        self.MIN_CLEARANCE = context.get_threshold("MIN_CLEARANCE", 5.0)  # meters

        self.MSG_RATE_MIN_HZ = context.get_threshold("MSG_RATE_MIN_HZ", 5.0)  # Hz
        self.HEARTBEAT_MAX_AGE = context.get_threshold("HEARTBEAT_MAX_AGE", 3.0)  # seconds

        self.BATTERY_RESERVE_PCT = context.get_threshold(
            "BATTERY_RESERVE_PCT",
            context.get_threshold("BATTERY_MIN_PERCENT", 15.0),
        )  # %
        self.BATTERY_RESERVE_AH = context.get_threshold("BATTERY_RESERVE_AH", 2.0)  # Ah

        self.NFZ_BUFFER_M = context.get_threshold("NFZ_BUFFER_M", 50.0)  # meters

        # RC + sensors + GNSS interference thresholds
        self.RC_RSSI_MIN = context.get_threshold("RC_RSSI_MIN", 35.0)  # percent
        self.COMPASS_HEALTH_REQUIRED = context.get_threshold("COMPASS_HEALTH_REQUIRED", True)
        self.GNSS_INTERFERENCE_WARN = context.get_threshold("GNSS_INTERFERENCE_WARN", 0.6)  # 0..1 (if provided)
        self.GNSS_INTERFERENCE_FAIL = context.get_threshold("GNSS_INTERFERENCE_FAIL", 0.85)  # 0..1 (if provided)

        # Storage
        self.LOG_FREE_MB_MIN = context.get_threshold("LOG_FREE_MB_MIN", 100.0)

    # -------------------------
    # Helpers
    # -------------------------

    def _value(self, *names: str) -> Any:
        """Return first non-None telemetry attribute among aliases."""
        for name in names:
            if hasattr(self.v, name):
                val = getattr(self.v, name)
                if val is not None:
                    return val
        return None

    def _ok(self, name: str, message: Optional[str] = None) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.PASS, message=message)

    def _fail(self, name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.FAIL, message=message)

    def _warn(self, name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.WARN, message=message)

    def _skip(self, name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.SKIP, message=message)


    @staticmethod
    def _as_latlon(point: Any) -> Optional[Tuple[float, float]]:
        """Best-effort extraction of (lat, lon) from tuples/dicts/objects."""
        try:
            if isinstance(point, (tuple, list)) and len(point) >= 2:
                return float(point[0]), float(point[1])
            if isinstance(point, dict) and "lat" in point and "lon" in point:
                return float(point["lat"]), float(point["lon"])
            if hasattr(point, "lat") and hasattr(point, "lon"):
                return float(getattr(point, "lat")), float(getattr(point, "lon"))
            if hasattr(point, "latitude") and hasattr(point, "longitude"):
                return float(getattr(point, "latitude")), float(getattr(point, "longitude"))
        except Exception:
            return None
        return None

    def _normalize_polygon(self, polygon: Iterable[Any]) -> List[Tuple[float, float]]:
        pts: List[Tuple[float, float]] = []
        for p in polygon:
            ll = self._as_latlon(p)
            if ll is not None:
                pts.append(ll)
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts.pop()
        return pts

    @staticmethod
    def _point_in_polygon(lat: float, lon: float, polygon: Sequence[Tuple[float, float]]) -> bool:
        """Ray-casting point-in-polygon using lat/lon as local planar coordinates."""
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

    @staticmethod
    def _dedupe_by_name(results: List[CheckResult]) -> List[CheckResult]:
        seen = set()
        out: List[CheckResult] = []
        for r in results:
            if getattr(r, "name", None) in seen:
                continue
            seen.add(r.name)
            out.append(r)
        return out

    @staticmethod
    def _has_fail(results: List[CheckResult]) -> bool:
        return any(r.status == CheckStatus.FAIL for r in results)

    # -------------------------
    # Core checks (return List[CheckResult])
    # -------------------------

    async def check_link_health(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        hb_age = self._value("heartbeat_age_s")
        if hb_age is None:
            results.append(self._skip("Heartbeat Age", "Heartbeat age not available"))
        elif hb_age <= self.HEARTBEAT_MAX_AGE:
            results.append(self._ok("Heartbeat Age", f"{hb_age:.2f}s"))
        else:
            results.append(self._fail("Heartbeat Age", f"{hb_age:.2f}s > {self.HEARTBEAT_MAX_AGE:.2f}s"))

        msg_rate = self._value("msg_rate_hz")
        if msg_rate is None:
            results.append(self._skip("Message Rate", "Message rate not available"))
        elif msg_rate >= self.MSG_RATE_MIN_HZ:
            results.append(self._ok("Message Rate", f"{msg_rate:.2f} Hz"))
        else:
            results.append(self._fail("Message Rate", f"{msg_rate:.2f} Hz < {self.MSG_RATE_MIN_HZ:.2f} Hz"))

        return results

    async def check_vehicle_readiness(self, allowed_modes: Optional[Sequence[str]] = None) -> List[CheckResult]:
        results: List[CheckResult] = []

        is_armable = self._value("is_armable")
        if is_armable is None:
            results.append(self._skip("Vehicle Armable", "Armable state not available"))
        elif bool(is_armable):
            results.append(self._ok("Vehicle Armable"))
        else:
            results.append(self._fail("Vehicle Armable", "Vehicle not armable (prearm/EKF checks failed)"))

        if allowed_modes:
            mode = self._value("current_mode", "mode")
            if mode is None:
                results.append(self._skip("Flight Mode", "Mode not available"))
            elif mode in allowed_modes:
                results.append(self._ok("Flight Mode", str(mode)))
            else:
                results.append(self._fail("Flight Mode", f"Mode '{mode}' not in allowed modes {list(allowed_modes)}"))

        return results

    async def check_arming_checks(self) -> List[CheckResult]:
        """
        Best-effort arming checks flags / prearm status.
        Supports multiple common telemetry conventions.
        """
        results: List[CheckResult] = []

        # Common booleans / strings / lists
        ok_flag = self._value("arming_checks_ok", "prearm_ok")
        if ok_flag is not None:
            if bool(ok_flag):
                results.append(self._ok("Arming Checks", "OK"))
            else:
                # Try to surface reason list/string
                reasons = self._value("prearm_errors", "arming_check_errors", "arming_fail_reasons")
                if reasons:
                    results.append(self._fail("Arming Checks", f"Failed: {reasons}"))
                else:
                    results.append(self._fail("Arming Checks", "Failed"))
            return results

        # Bitmask style (project-specific); if present, just surface it
        mask = self._value("arming_check_flags", "prearm_flags")
        if mask is not None:
            # Without a decoding table, we can only WARN when non-zero.
            if int(mask) == 0:
                results.append(self._ok("Arming Checks", "Flags=0"))
            else:
                results.append(self._warn("Arming Checks", f"Flags={int(mask)} (decode not implemented)"))
            return results

        return [self._skip("Arming Checks", "Arming checks telemetry not available")]

    async def check_gps_quality(
            self,
            timeout_s: float = 30.0,
            poll_interval_s: float = 1.0,
            required_stable_reads: int = 3,
    ) -> List[CheckResult]:
        start = time.monotonic()
        stable = 0
        last_results: List[CheckResult] = []

        def eval_once() -> List[CheckResult]:
            r: List[CheckResult] = []

            fix = self._value("gps_fix_type")
            if fix is None:
                r.append(self._skip("GPS Fix Type", "gps_fix_type not available"))
            elif fix >= self.GPS_FIX_TYPE_MIN:
                r.append(self._ok("GPS Fix Type", f"{fix}"))
            else:
                r.append(self._fail("GPS Fix Type", f"Fix type {fix} < {self.GPS_FIX_TYPE_MIN}"))

            hdop_raw = self._value("hdop")
            hdop = (float(hdop_raw) / 100.0) if hdop_raw is not None else None
            if hdop is None:
                r.append(self._skip("GPS HDOP", "hdop not available"))
            elif float(hdop) <= float(self.HDOP_MAX):
                r.append(self._ok("GPS HDOP", f"{float(hdop):.2f}"))
            else:
                r.append(self._fail("GPS HDOP", f"HDOP {float(hdop):.2f} > {float(self.HDOP_MAX):.2f}"))

            sats = self._value("satellites_visible")
            if sats is None:
                r.append(self._skip("GPS Satellites", "satellites_visible not available"))
            elif int(sats) >= int(self.SAT_MIN):
                r.append(self._ok("GPS Satellites", f"{int(sats)}"))
            else:
                r.append(self._fail("GPS Satellites", f"Sats {int(sats)} < {int(self.SAT_MIN)}"))

            pos_unc = self._value("pos_uncertainty_m")
            if pos_unc is not None:
                pos_unc_max = self._value("pos_uncertainty_max")
                threshold = float(pos_unc_max) if pos_unc_max is not None else 5.0
                if float(pos_unc) <= threshold:
                    r.append(self._ok("Position Uncertainty", f"{float(pos_unc):.2f}m"))
                else:
                    r.append(self._fail("Position Uncertainty", f"{float(pos_unc):.2f}m > {threshold:.2f}m"))

            return r

        def no_fail(r: List[CheckResult]) -> bool:
            return not any(x.status == CheckStatus.FAIL for x in r)

        while True:
            last_results = eval_once()
            stable = stable + 1 if no_fail(last_results) else 0

            if stable >= required_stable_reads:
                return last_results

            if time.monotonic() - start >= timeout_s:
                return last_results

            await asyncio.sleep(poll_interval_s)

    async def check_ekf_health(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        ekf_ok = self._value("ekf_ok")
        if ekf_ok is None:
            results.append(self._skip("EKF Health", "ekf_ok not available"))
        elif bool(ekf_ok):
            results.append(self._ok("EKF Health"))
        else:
            results.append(self._fail("EKF Health", "EKF not OK"))

        innov = self._value("innovation_consistency")
        if innov is not None:
            innov_max = self._value("innovation_consistency_max")
            if innov_max is None:
                innov_max = self.EKF_THRESHOLD
            if innov_max is not None and float(innov) <= float(innov_max):
                results.append(self._ok("EKF Innovation", f"{float(innov):.3f}"))
            elif innov_max is not None:
                results.append(self._fail("EKF Innovation", f"{float(innov):.3f} > {float(innov_max):.3f}"))
            else:
                results.append(self._warn("EKF Innovation", f"{float(innov):.3f} (no max threshold)"))

        return results

    async def check_home_position(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        home_set = self._value("home_set")
        if home_set is None:
            results.append(self._skip("Home Set", "home_set not available"))
        elif bool(home_set):
            results.append(self._ok("Home Set"))
        else:
            results.append(self._fail("Home Set", "Home position not set"))

        lat = self._value("lat")
        lon = self._value("lon")
        home_lat = self._value("home_lat")
        home_lon = self._value("home_lon")

        if None in (lat, lon, home_lat, home_lon):
            results.append(self._skip("Distance to Home", "Current/home coordinates not available"))
            return results

        dist_m = haversine_km(float(lat), float(lon), float(home_lat), float(home_lon)) * 1000.0
        if dist_m <= float(self.HOME_MAX_DIST):
            results.append(self._ok("Distance to Home", f"{dist_m:.1f} m"))
        else:
            results.append(self._fail("Distance to Home", f"{dist_m:.1f} m > {float(self.HOME_MAX_DIST):.1f} m"))

        return results

    async def check_wind(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        wind = self.ctx.get_wind_speed() if hasattr(self.ctx, "get_wind_speed") else None
        gust = self.ctx.get_wind_gust() if hasattr(self.ctx, "get_wind_gust") else None

        if wind is None:
            results.append(self._skip("Wind Speed", "Wind speed not available"))
        elif float(wind) <= float(self.WIND_MAX):
            results.append(self._ok("Wind Speed", f"{float(wind):.1f} m/s"))
        else:
            results.append(self._fail("Wind Speed", f"{float(wind):.1f} m/s > {float(self.WIND_MAX):.1f} m/s"))

        if gust is None:
            results.append(self._skip("Wind Gust", "Wind gust not available"))
        elif float(gust) <= float(self.GUST_MAX):
            results.append(self._ok("Wind Gust", f"{float(gust):.1f} m/s"))
        else:
            results.append(self._fail("Wind Gust", f"{float(gust):.1f} m/s > {float(self.GUST_MAX):.1f} m/s"))

        return results

    async def check_battery(
            self,
            estimated_time_s: Optional[float] = None,
            mission_ah_req: Optional[float] = None,
    ) -> List[CheckResult]:
        results: List[CheckResult] = []

        v_batt = self._value("v_batt", "battery_voltage")
        v_min = self._value("v_min")
        if v_min is None:
            v_min = self.BATTERY_MIN_V

        if v_batt is None:
            results.append(self._skip("Battery Voltage", "Battery voltage not available"))
        elif v_min is None:
            results.append(self._ok("Battery Voltage", f"{float(v_batt):.2f} V (no minimum threshold)"))
        elif float(v_batt) >= float(v_min):
            results.append(self._ok("Battery Voltage", f"{float(v_batt):.2f} V"))
        else:
            results.append(self._fail("Battery Voltage", f"{float(v_batt):.2f} V < {float(v_min):.2f} V"))

        # Estimate mission time if possible
        if estimated_time_s is None and getattr(self.ctx, "mission", None) is not None:
            try:
                total_dist = self.ctx.total_distance() if hasattr(self.ctx, "total_distance") else None
                speed = getattr(self.ctx.mission, "speed", None)
                if total_dist is not None and speed and float(speed) > 0:
                    estimated_time_s = float(total_dist) / float(speed)
            except Exception:
                pass

        max_flight_time_s = self._value("max_flight_time_s")
        remaining_pct = self._value("battery_remaining_pct", "battery_remaining")

        if estimated_time_s and max_flight_time_s and remaining_pct is not None:
            required_pct = (float(estimated_time_s) / float(max_flight_time_s)) * 100.0
            needed = required_pct + float(self.BATTERY_RESERVE_PCT)
            remaining = float(remaining_pct)

            if remaining >= needed:
                results.append(self._ok("Battery Budget (%)", f"Remaining {remaining:.1f}% >= Needed {needed:.1f}%"))
            else:
                results.append(self._fail("Battery Budget (%)", f"Remaining {remaining:.1f}% < Needed {needed:.1f}%"))
        else:
            results.append(self._skip("Battery Budget (%)", "Insufficient data for % budget"))

        remaining_ah = self._value("battery_remaining_Ah")
        if mission_ah_req is not None and remaining_ah is not None:
            margin = float(remaining_ah) - float(mission_ah_req)
            if margin >= float(self.BATTERY_RESERVE_AH):
                results.append(self._ok("Battery Budget (Ah)", f"Margin {margin:.2f} Ah"))
            else:
                results.append(self._fail("Battery Budget (Ah)", f"Margin {margin:.2f} Ah < {float(self.BATTERY_RESERVE_AH):.2f} Ah"))
        elif mission_ah_req is not None:
            results.append(self._skip("Battery Budget (Ah)", "Ah data not available"))

        return results

    async def check_failsafe_config(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        rtl_alt = self._value("rtl_alt_m")
        if rtl_alt is None:
            results.append(self._skip("RTL Altitude", "rtl_alt_m not available"))
        elif float(rtl_alt) >= float(self.RTL_MIN_ALT):
            results.append(self._ok("RTL Altitude", f"{float(rtl_alt):.1f} m"))
        else:
            results.append(self._fail("RTL Altitude", f"{float(rtl_alt):.1f} m < {float(self.RTL_MIN_ALT):.1f} m"))

        batt_fs = self._value("battery_failsafe_enabled")
        if batt_fs is None:
            results.append(self._skip("Battery Failsafe", "battery_failsafe_enabled not available"))
        elif bool(batt_fs):
            results.append(self._ok("Battery Failsafe"))
        else:
            results.append(self._fail("Battery Failsafe", "Battery failsafe not enabled"))

        gf_action = self._value("geo_fence_action")
        if gf_action is None:
            results.append(self._skip("Geofence Action", "geo_fence_action not available"))
        elif int(gf_action) != 0:  # 0 = NONE
            results.append(self._ok("Geofence Action", f"{int(gf_action)}"))
        else:
            results.append(self._fail("Geofence Action", "Geofence action set to NONE"))

        return results

    async def check_geofence(self) -> List[CheckResult]:
        """
        Validate current position against a configured geofence polygon when available.
        If no polygon is configured for this run, treat as SKIP.
        """
        raw_poly = getattr(self.ctx, "geofence_polygon", None)
        if not raw_poly:
            return [self._skip("Geofence", "No geofence polygon")]

        poly = self._normalize_polygon(raw_poly)
        if len(poly) < 3:
            return [self._fail("Geofence", "Invalid geofence polygon")]

        lat = self._value("lat")
        lon = self._value("lon")
        if lat is None or lon is None:
            return [self._skip("Geofence", "Current position unavailable")]

        if self._point_in_polygon(float(lat), float(lon), poly):
            return [self._ok("Geofence", "Current position inside")]
        return [self._fail("Geofence", "Current position outside geofence")]

    async def check_terrain_clearance(self) -> List[CheckResult]:
        """
        Validate terrain clearance.
        Priority:
          1) direct telemetry AGL/terrain-clearance fields when present
          2) fallback to waypoint altitude minus cached terrain data
        """
        agl = self._value("altitude_terrain_m", "agl_m", "height_agl_m")
        if agl is not None:
            agl_f = float(agl)
            if agl_f < float(self.MIN_CLEARANCE):
                return [self._fail("Terrain Clearance", f"{agl_f:.1f}m < {float(self.MIN_CLEARANCE):.1f}m")]
            return [self._ok("Terrain Clearance", f"{agl_f:.1f}m")]

        waypoints = getattr(self.ctx.mission, "waypoints", None)
        if not waypoints:
            return [self._skip("Terrain Clearance", "No waypoints")]
        if not hasattr(self.ctx, "get_waypoint_terrain"):
            return [self._skip("Terrain Clearance", "No cached terrain in context")]

        for i, wp in enumerate(waypoints):
            terrain = self.ctx.get_waypoint_terrain(i)
            if asyncio.iscoroutine(terrain):
                terrain = await terrain

            if terrain is None:
                return [self._warn("Terrain Clearance", f"Terrain missing at waypoint {i}")]

            wp_alt = getattr(wp, "alt", None)
            if wp_alt is None:
                return [self._warn("Terrain Clearance", f"Waypoint {i} missing alt")]

            clearance = float(wp_alt) - float(terrain)
            if clearance < float(self.MIN_CLEARANCE):
                return [
                    self._fail(
                        "Terrain Clearance",
                        f"WP{i} clearance {clearance:.1f}m < {float(self.MIN_CLEARANCE):.1f}m"
                    )
                ]

        return [self._ok("Terrain Clearance", f"Min clearance >= {float(self.MIN_CLEARANCE):.1f}m")]


    # -------------------------
    # Additional common checks
    # -------------------------

    async def check_rc_link(self) -> List[CheckResult]:
        """
        RC link presence/quality. Best-effort.
        Looks for:
          - rc_link_ok / rc_present boolean
          - rc_rssi (0..100) threshold
          - rc_failsafe boolean (FAIL if active)
        """
        results: List[CheckResult] = []

        rc_failsafe = self._value("rc_failsafe", "failsafe_rc")
        if rc_failsafe is not None and bool(rc_failsafe):
            results.append(self._fail("RC Link", "RC failsafe active"))
            return results

        rc_ok = self._value("rc_link_ok", "rc_present", "rc_ok")
        if rc_ok is not None:
            if bool(rc_ok):
                results.append(self._ok("RC Link", "Present"))
            else:
                results.append(self._fail("RC Link", "Not present"))
                return results
        else:
            results.append(self._skip("RC Link", "RC presence not available"))

        rssi = self._value("rc_rssi", "rssi", "rc_signal_percent")
        if rssi is None:
            results.append(self._skip("RC RSSI", "RC RSSI not available"))
        else:
            rssi_f = float(rssi)
            if rssi_f >= float(self.RC_RSSI_MIN):
                results.append(self._ok("RC RSSI", f"{rssi_f:.0f}%"))
            else:
                results.append(self._warn("RC RSSI", f"{rssi_f:.0f}% < {float(self.RC_RSSI_MIN):.0f}%"))

        return results

    async def check_compass_health(self) -> List[CheckResult]:
        """
        Compass health/calibration. Best-effort.
        """
        results: List[CheckResult] = []

        healthy = self._value("compass_healthy", "mag_healthy")
        if healthy is None:
            results.append(self._skip("Compass Health", "Compass health not available"))
        elif bool(healthy):
            results.append(self._ok("Compass Health"))
        else:
            # If compass health required, FAIL; else WARN.
            if bool(self.COMPASS_HEALTH_REQUIRED):
                results.append(self._fail("Compass Health", "Compass unhealthy"))
            else:
                results.append(self._warn("Compass Health", "Compass unhealthy"))

        calibrated = self._value("compass_calibrated", "mag_calibrated")
        if calibrated is None:
            results.append(self._skip("Compass Calibration", "Compass calibration not available"))
        elif bool(calibrated):
            results.append(self._ok("Compass Calibration"))
        else:
            results.append(self._warn("Compass Calibration", "Compass not calibrated"))

        return results

    async def check_imu_calibration(self) -> List[CheckResult]:
        """
        IMU calibration / sensor readiness. Best-effort.
        """
        results: List[CheckResult] = []

        imu_cal = self._value("imu_calibrated")
        accel_cal = self._value("accel_calibrated")
        gyro_cal = self._value("gyro_calibrated")

        if imu_cal is None and accel_cal is None and gyro_cal is None:
            return [self._skip("IMU Calibration", "IMU calibration telemetry not available")]

        # Prefer imu_calibrated when present
        if imu_cal is not None:
            if bool(imu_cal):
                results.append(self._ok("IMU Calibration"))
            else:
                results.append(self._fail("IMU Calibration", "IMU not calibrated"))
            return results

        if accel_cal is not None:
            results.append(self._ok("Accel Calibration") if bool(accel_cal) else self._fail("Accel Calibration", "Accel not calibrated"))
        if gyro_cal is not None:
            results.append(self._ok("Gyro Calibration") if bool(gyro_cal) else self._fail("Gyro Calibration", "Gyro not calibrated"))

        return results

    async def check_storage_logging(self) -> List[CheckResult]:
        """
        Storage/logging availability. Best-effort.
        """
        results: List[CheckResult] = []

        sd_present = self._value("sdcard_present", "log_storage_present")
        if sd_present is None:
            results.append(self._skip("Log Storage", "Storage presence not available"))
        elif bool(sd_present):
            results.append(self._ok("Log Storage", "Present"))
        else:
            results.append(self._warn("Log Storage", "Not present"))

        logging_enabled = self._value("logging_enabled", "log_enabled")
        if logging_enabled is None:
            results.append(self._skip("Logging Enabled", "Logging enable flag not available"))
        elif bool(logging_enabled):
            results.append(self._ok("Logging Enabled"))
        else:
            results.append(self._warn("Logging Enabled", "Logging disabled"))

        free_mb = self._value("log_free_mb", "storage_free_mb", "sd_free_mb")
        if free_mb is None:
            results.append(self._skip("Log Free Space", "Free space not available"))
        else:
            free_mb_f = float(free_mb)
            if free_mb_f >= float(self.LOG_FREE_MB_MIN):
                results.append(self._ok("Log Free Space", f"{free_mb_f:.0f} MB"))
            else:
                results.append(self._warn("Log Free Space", f"{free_mb_f:.0f} MB < {float(self.LOG_FREE_MB_MIN):.0f} MB"))

        return results

    async def check_gnss_interference(self) -> List[CheckResult]:
        """
        GNSS jamming/interference. Best-effort.
        If provided, expects a normalized 0..1 interference metric, or a dB/ratio metric that your telemetry defines.
        """
        metric = self._value("gnss_interference", "gps_interference", "gps_jamming_indicator", "gnss_jamming")
        if metric is None:
            # Some stacks provide "noise_per_ms" or "jamming_level"
            noise = self._value("noise_per_ms", "gps_noise")
            if noise is None:
                return [self._skip("GNSS Interference", "Interference telemetry not available")]
            # Without a threshold definition, surface as WARN/INFO only.
            return [self._warn("GNSS Interference", f"Noise={noise} (no thresholds)")]

        try:
            m = float(metric)
        except Exception:
            return [self._warn("GNSS Interference", f"Value={metric} (unparseable)")]

        if m >= float(self.GNSS_INTERFERENCE_FAIL):
            return [self._fail("GNSS Interference", f"{m:.2f} >= {float(self.GNSS_INTERFERENCE_FAIL):.2f}")]
        if m >= float(self.GNSS_INTERFERENCE_WARN):
            return [self._warn("GNSS Interference", f"{m:.2f} >= {float(self.GNSS_INTERFERENCE_WARN):.2f}")]
        return [self._ok("GNSS Interference", f"{m:.2f}")]

    # -------------------------
    # Mission integrity (optional)
    # -------------------------

    async def check_mission_integrity(
            self,
            mission_waypoints: Sequence[Any],
            expected_count: int,
            mission_crc: Optional[int],
    ) -> List[CheckResult]:
        results: List[CheckResult] = []

        if len(mission_waypoints) == int(expected_count):
            results.append(self._ok("Mission Count", f"{len(mission_waypoints)}"))
        else:
            results.append(self._fail("Mission Count", f"Got {len(mission_waypoints)}, expected {int(expected_count)}"))

        current_crc = getattr(self.v, "mission_crc", None)
        if mission_crc is None:
            results.append(self._skip("Mission CRC", "No CRC provided"))
        elif current_crc is None:
            results.append(self._skip("Mission CRC", "Vehicle mission_crc not available"))
        elif int(mission_crc) == int(current_crc):
            results.append(self._ok("Mission CRC"))
        else:
            results.append(self._fail("Mission CRC", "Mission CRC mismatch"))

        return results

    # -------------------------
    # Priority runner
    # -------------------------

    def _specs(
            self,
            *,
            estimated_time_s: Optional[float],
            mission_ah_req: Optional[float],
            allowed_modes: Optional[List[str]],
            gps_timeout_s: float,
            mission_waypoints: Optional[List[Any]],
            expected_mission_count: Optional[int],
            mission_crc: Optional[int],
    ) -> List[CheckSpec]:
        specs: List[CheckSpec] = [
            # ---- CRITICAL gates ----
            CheckSpec("Link Health", Priority.CRITICAL, True, lambda: self.check_link_health()),
            CheckSpec("Arming Checks", Priority.CRITICAL, True, lambda: self.check_arming_checks()),
            CheckSpec("Vehicle Readiness", Priority.CRITICAL, True, lambda: self.check_vehicle_readiness(allowed_modes=allowed_modes)),
            CheckSpec("GPS Quality", Priority.CRITICAL, True, lambda: self.check_gps_quality(timeout_s=gps_timeout_s)),
            CheckSpec("EKF Health", Priority.CRITICAL, True, lambda: self.check_ekf_health()),
            CheckSpec("Battery", Priority.CRITICAL, True, lambda: self.check_battery(estimated_time_s=estimated_time_s, mission_ah_req=mission_ah_req)),

            # ---- SAFETY checks ----
            CheckSpec("Failsafe Config", Priority.SAFETY, True, lambda: self.check_failsafe_config()),
            CheckSpec("Home Position", Priority.SAFETY, True, lambda: self.check_home_position()),
            CheckSpec("Wind", Priority.SAFETY, False, lambda: self.check_wind()),
            CheckSpec("Geofence", Priority.SAFETY, True, lambda: self.check_geofence()),
            CheckSpec("Terrain Clearance", Priority.SAFETY, True, lambda: self.check_terrain_clearance()),

            # ---- QUALITY diagnostics ----
            CheckSpec("RC Link", Priority.QUALITY, False, lambda: self.check_rc_link()),
            CheckSpec("Compass", Priority.QUALITY, False, lambda: self.check_compass_health()),
            CheckSpec("IMU", Priority.QUALITY, False, lambda: self.check_imu_calibration()),
            CheckSpec("Storage/Logging", Priority.QUALITY, False, lambda: self.check_storage_logging()),
            CheckSpec("GNSS Interference", Priority.QUALITY, False, lambda: self.check_gnss_interference()),
        ]

        if mission_waypoints is not None and expected_mission_count is not None:
            specs.append(
                CheckSpec(
                    "Mission Integrity",
                    Priority.QUALITY,
                    False,
                    lambda: self.check_mission_integrity(
                        mission_waypoints=mission_waypoints,
                        expected_count=expected_mission_count,
                        mission_crc=mission_crc,
                    ),
                )
            )

        # Stable sort by priority (IntEnum order), then keep insertion order within same priority
        return sorted(specs, key=lambda s: int(s.priority))

    async def run(
            self,
            estimated_time_s: Optional[float] = None,
            mission_waypoints: Optional[List[Any]] = None,
            expected_mission_count: Optional[int] = None,
            mission_crc: Optional[int] = None,
            mission_ah_req: Optional[float] = None,
            allowed_modes: Optional[List[str]] = None,
            gps_timeout_s: float = 30.0,
            fail_fast: bool = True,
            concurrent_within_priority: bool = True,
    ) -> List[CheckResult]:
        """
        Executes checks in priority order.

        - fail_fast=True: if any CRITICAL/SAFETY gate FAILs, remaining lower-priority checks are SKIPped.
        - concurrent_within_priority=True: runs checks of same priority concurrently.
        """
        specs = self._specs(
            estimated_time_s=estimated_time_s,
            mission_ah_req=mission_ah_req,
            allowed_modes=allowed_modes,
            gps_timeout_s=gps_timeout_s,
            mission_waypoints=mission_waypoints,
            expected_mission_count=expected_mission_count,
            mission_crc=mission_crc,
        )

        results: List[CheckResult] = []
        gates_failed = False
        last_priority: Optional[Priority] = None
        batch: List[CheckSpec] = []

        async def run_spec(spec: CheckSpec) -> List[CheckResult]:
            try:
                out = await spec.coro()
                return out if isinstance(out, list) else [out]
            except Exception as e:
                # preflight should be resilient; convert exceptions to FAIL for gates, WARN otherwise
                if spec.is_gate:
                    return [self._fail(spec.name, f"Exception: {type(e).__name__}: {e}")]
                return [self._warn(spec.name, f"Exception: {type(e).__name__}: {e}")]

        async def flush_batch() -> None:
            nonlocal gates_failed, results, batch, last_priority

            if not batch:
                return

            # If we already failed gates and we're fail-fast, skip remaining batches
            if fail_fast and gates_failed:
                for s in batch:
                    results.append(self._skip(s.name, "Skipped due to previous gate failure"))
                batch = []
                return

            if concurrent_within_priority and len(batch) > 1:
                groups = await asyncio.gather(*(run_spec(s) for s in batch), return_exceptions=False)
                flat: List[CheckResult] = []
                for g in groups:
                    flat.extend(g)
            else:
                flat = []
                for s in batch:
                    flat.extend(await run_spec(s))

            results.extend(flat)

            # Update gate-failure state
            if fail_fast:
                for s in batch:
                    if s.is_gate:
                        # Determine if this spec produced any FAIL
                        spec_results = [r for r in flat if r.name == s.name or r.name.startswith(s.name)]
                        if any(r.status == CheckStatus.FAIL for r in spec_results):
                            gates_failed = True
                            break

            batch = []

        # Group by priority and flush per priority
        for spec in specs:
            if last_priority is None:
                last_priority = spec.priority
                batch.append(spec)
                continue

            if spec.priority != last_priority:
                await flush_batch()
                last_priority = spec.priority
                batch.append(spec)
            else:
                batch.append(spec)

        await flush_batch()

        # Deduplicate by name (defensive)
        results = self._dedupe_by_name(results)

        # Final ordering: priority buckets first, then status severity within each bucket
        status_rank = {
            CheckStatus.FAIL: 0,
            CheckStatus.WARN: 1,
            CheckStatus.PASS: 2,
            CheckStatus.SKIP: 3,
        }

        # Create a map from spec-name to priority (for ordering)
        prio_map = {s.name: s.priority for s in specs}

        def result_priority(r: CheckResult) -> int:
            # If name matches spec, use it; else default to INFO
            return int(prio_map.get(r.name, Priority.INFO))

        results.sort(key=lambda r: (result_priority(r), status_rank.get(r.status, 99), r.name))
        return results
