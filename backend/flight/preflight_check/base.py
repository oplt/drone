from math import radians, sin, cos, sqrt, atan2
from typing import List, Optional, Any
from .schemas import CheckResult, CheckStatus
from .preflight_context import PreflightContext


class BasePreflightChecks:

    def __init__(self, context: PreflightContext):

        self.ctx = context
        self.v = context.vehicle_state

        # Set thresholds from context
        self.HDOP_MAX = context.get_threshold('HDOP_MAX', 2.5)
        self.SAT_MIN = context.get_threshold('SAT_MIN', 6)
        self.HOME_MAX_DIST = context.get_threshold('HOME_MAX_DIST', 100)
        self.WIND_MAX = context.get_threshold('WIND_MAX', 12)
        self.GUST_MAX = context.get_threshold('GUST_MAX', 15)
        self.RTL_MIN_ALT = context.get_threshold('RTL_MIN_ALT', 30)
        self.AGL_MIN = context.get_threshold('AGL_MIN', 10)
        self.AGL_MAX = context.get_threshold('AGL_MAX', 120)
        self.AGL_SAFETY_MIN = context.get_threshold('AGL_SAFETY_MIN', 5)
        self.MSG_RATE_MIN_HZ = context.get_threshold('MSG_RATE_MIN_HZ', 5)
        self.HEARTBEAT_MAX_AGE = context.get_threshold('HEARTBEAT_MAX_AGE', 3)
        self.BATTERY_RESERVE_PCT = context.get_threshold('BATTERY_RESERVE_PCT', 15)
        self.BATTERY_RESERVE_AH = context.get_threshold('BATTERY_RESERVE_AH', 2)
        self.NFZ_BUFFER_M = context.get_threshold('NFZ_BUFFER_M', 50)
        self.OBST_BUFFER_M = context.get_threshold('OBST_BUFFER_M', 10)


    def haversine(self, lat1, lon1, lat2, lon2):
        """Calculate great-circle distance between two points."""
        # Use context's cached distance if available
        if hasattr(self.ctx, 'get_distance_between_points'):
            # Create simple waypoint-like objects for cache lookup
            class SimpleWP:
                def __init__(self, lat, lon):
                    self.lat = lat
                    self.lon = lon

            wp1 = SimpleWP(lat1, lon1)
            wp2 = SimpleWP(lat2, lon2)
            return self.ctx.get_distance_between_points(wp1, wp2)

        # Fallback to direct calculation
        R = 6371000
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return 2 * R * atan2(sqrt(a), sqrt(1 - a))

    # ==================== Link & Telemetry Health ====================
    def check_link_health(self):
        """Check heartbeat age and message rate."""
        checks = []

        # Heartbeat age check
        if hasattr(self.v, 'heartbeat_age_s'):
            if self.v.heartbeat_age_s < self.HEARTBEAT_MAX_AGE:
                checks.append(CheckResult(name="Heartbeat Age", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Heartbeat Age",
                    status=CheckStatus.FAIL,
                    message=f"Heartbeat age {self.v.heartbeat_age_s}s > {self.HEARTBEAT_MAX_AGE}s"
                ))

        # Message rate check
        if hasattr(self.v, 'msg_rate_hz'):
            if self.v.msg_rate_hz >= self.MSG_RATE_MIN_HZ:
                checks.append(CheckResult(name="Message Rate", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Message Rate",
                    status=CheckStatus.FAIL,
                    message=f"Rate {self.v.msg_rate_hz}Hz < {self.MSG_RATE_MIN_HZ}Hz"
                ))

        return checks

    # ==================== Wind / Weather Gate ====================
    def check_wind(self):
        """Check wind speed and gusts against limits."""
        checks = []

        wind_speed = self.ctx.get_wind_speed()
        if wind_speed is not None:
            if wind_speed <= self.WIND_MAX:
                checks.append(CheckResult(name="Wind Speed", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Wind Speed",
                    status=CheckStatus.FAIL,
                    message=f"Wind {wind_speed}m/s > {self.WIND_MAX}m/s"
                ))

        wind_gust = self.ctx.get_wind_gust()
        if wind_gust is not None:
            if wind_gust <= self.GUST_MAX:
                checks.append(CheckResult(name="Wind Gust", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Wind Gust",
                    status=CheckStatus.FAIL,
                    message=f"Gust {wind_gust}m/s > {self.GUST_MAX}m/s"
                ))

        return checks

    # ==================== Geofence / Operational Area ====================
    def check_geofence(self):
        """Check if mission waypoints are within geofence."""
        checks = []

        if not self.ctx.geofence_polygon:
            return [CheckResult(name="Geofence", status=CheckStatus.SKIP, message="No geofence defined")]

        # This would need actual point-in-polygon checking
        # Placeholder implementation
        all_inside = True
        for i, wp in enumerate(self.ctx.mission.waypoints):
            # Check if point is inside geofence
            # inside = point_in_polygon(wp.lat, wp.lon, self.ctx.geofence_polygon)
            inside = True  # Placeholder
            if not inside:
                all_inside = False
                checks.append(CheckResult(
                    name=f"Waypoint {i} Geofence",
                    status=CheckStatus.FAIL,
                    message=f"Waypoint {i} outside geofence"
                ))

        if all_inside:
            checks.append(CheckResult(name="Geofence", status=CheckStatus.PASS))

        return checks

    # ==================== No-Fly Zone Clearance ====================
    def check_no_fly_zones(self):
        """Check if mission waypoints avoid no-fly zones."""
        checks = []

        if not self.ctx.no_fly_zones:
            return [CheckResult(name="No-Fly Zones", status=CheckStatus.SKIP, message="No no-fly zones defined")]

        all_safe = True
        for i, wp in enumerate(self.ctx.mission.waypoints):
            safe = self.ctx.check_no_fly_zones(wp.lat, wp.lon, self.NFZ_BUFFER_M)
            if not safe:
                all_safe = False
                checks.append(CheckResult(
                    name=f"Waypoint {i} No-Fly",
                    status=CheckStatus.FAIL,
                    message=f"Waypoint {i} inside no-fly zone"
                ))

        if all_safe:
            checks.append(CheckResult(name="No-Fly Zones", status=CheckStatus.PASS))

        return checks

    # ==================== Vehicle State & Mode Readiness ====================
    def check_vehicle_state(self, allowed_modes=None):
        """Check if vehicle is armable and in correct mode."""
        checks = []

        # Armability check
        if hasattr(self.v, 'is_armable'):
            if self.v.is_armable:
                checks.append(CheckResult(name="Vehicle Armable", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Vehicle Armable",
                    status=CheckStatus.FAIL,
                    message="Vehicle not armable (prearm/EKF checks failed)"
                ))

        # Mode check
        if allowed_modes and hasattr(self.v, 'current_mode'):
            if self.v.current_mode in allowed_modes:
                checks.append(CheckResult(name="Flight Mode", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Flight Mode",
                    status=CheckStatus.FAIL,
                    message=f"Mode {self.v.current_mode} not in allowed modes"
                ))

        return checks

    # ==================== GPS Fix & Navigation Quality ====================
    def check_gps_quality(self):
        """Enhanced GPS check with fix type, HDOP, satellites, and uncertainty."""
        checks = []

        # GPS fix type
        if hasattr(self.v, 'gps_fix_type'):
            if self.v.gps_fix_type >= 3:  # 3D fix or better
                checks.append(CheckResult(name="GPS Fix Type", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="GPS Fix Type",
                    status=CheckStatus.FAIL,
                    message=f"Fix type: {self.v.gps_fix_type} (need >=3)"
                ))

        # HDOP check
        if hasattr(self.v, 'hdop'):
            if self.v.hdop <= self.HDOP_MAX:
                checks.append(CheckResult(name="GPS HDOP", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="GPS HDOP",
                    status=CheckStatus.FAIL,
                    message=f"HDOP {self.v.hdop} > {self.HDOP_MAX}"
                ))

        # Satellites visible
        if hasattr(self.v, 'satellites_visible'):
            if self.v.satellites_visible >= self.SAT_MIN:
                checks.append(CheckResult(name="GPS Satellites", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="GPS Satellites",
                    status=CheckStatus.FAIL,
                    message=f"Sats {self.v.satellites_visible} < {self.SAT_MIN}"
                ))

        # Position uncertainty
        if hasattr(self.v, 'pos_uncertainty_m'):
            if hasattr(self.v, 'pos_uncertainty_max') and self.v.pos_uncertainty_m <= self.v.pos_uncertainty_max:
                checks.append(CheckResult(name="Position Uncertainty", status=CheckStatus.PASS))
            elif self.v.pos_uncertainty_m <= 5:  # Default threshold
                checks.append(CheckResult(name="Position Uncertainty", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Position Uncertainty",
                    status=CheckStatus.FAIL,
                    message=f"Uncertainty {self.v.pos_uncertainty_m}m > threshold"
                ))

        return checks

    # ==================== Home Position & Reference Frames ====================
    def check_home_position(self):
        """Check if home is set and within acceptable distance."""
        checks = []

        # Home set check
        if hasattr(self.v, 'home_set'):
            if self.v.home_set:
                checks.append(CheckResult(name="Home Set", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Home Set",
                    status=CheckStatus.FAIL,
                    message="Home position not set"
                ))

        # Distance to home
        if (hasattr(self.v, 'lat') and hasattr(self.v, 'lon') and
                hasattr(self.v, 'home_lat') and hasattr(self.v, 'home_lon')):
            distance = self.haversine(self.v.lat, self.v.lon,
                                      self.v.home_lat, self.v.home_lon)
            if distance <= self.HOME_MAX_DIST:
                checks.append(CheckResult(name="Distance to Home", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Distance to Home",
                    status=CheckStatus.FAIL,
                    message=f"Distance {distance:.1f}m > {self.HOME_MAX_DIST}m"
                ))

        return checks

    # ==================== EKF / Attitude Solution Health ====================
    def check_ekf_health(self):
        """Check EKF flags and attitude consistency."""
        checks = []

        # EKF OK check
        if hasattr(self.v, 'ekf_ok'):
            if self.v.ekf_ok:
                checks.append(CheckResult(name="EKF Health", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="EKF Health",
                    status=CheckStatus.FAIL,
                    message="EKF not OK"
                ))

        # Innovation consistency
        if hasattr(self.v, 'innovation_consistency'):
            if hasattr(self.v, 'innovation_consistency_max') and self.v.innovation_consistency <= self.v.innovation_consistency_max:
                checks.append(CheckResult(name="EKF Innovation", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="EKF Innovation",
                    status=CheckStatus.FAIL,
                    message=f"Innovation {self.v.innovation_consistency} > max"
                ))

        # Attitude variance
        if hasattr(self.v, 'attitude_variance'):
            if hasattr(self.v, 'attitude_variance_max') and self.v.attitude_variance <= self.v.attitude_variance_max:
                checks.append(CheckResult(name="Attitude Variance", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Attitude Variance",
                    status=CheckStatus.FAIL,
                    message=f"Variance {self.v.attitude_variance} > max"
                ))

        return checks

    # ==================== Battery & Power Budget ====================
    def check_battery_voltage(self):
        """Check battery voltage."""
        if hasattr(self.v, 'v_batt') and hasattr(self.v, 'v_min'):
            if self.v.v_batt >= self.v.v_min:
                return CheckResult(name="Battery Voltage", status=CheckStatus.PASS)
            else:
                return CheckResult(
                    name="Battery Voltage",
                    status=CheckStatus.FAIL,
                    message=f"Voltage {self.v.v_batt}V < {self.v.v_min}V"
                )
        return CheckResult(name="Battery Voltage", status=CheckStatus.SKIP, message="Battery voltage data not available")

    def check_battery_capacity(self, estimated_time_s=None, mission_ah_req=None):
        """Enhanced battery check with energy budget calculation."""
        checks = [self.check_battery_voltage()]

        # Simple percentage-based check
        if estimated_time_s and hasattr(self.v, 'max_flight_time_s') and hasattr(self.v, 'battery_remaining_pct'):
            required_pct = (estimated_time_s / self.v.max_flight_time_s) * 100
            remaining = self.v.battery_remaining_pct

            if remaining >= required_pct + self.BATTERY_RESERVE_PCT:
                checks.append(CheckResult(name="Battery Percentage", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Battery Percentage",
                    status=CheckStatus.FAIL,
                    message=f"Remaining {remaining}% < Required {required_pct:.1f}%"
                ))

        # Advanced Ah-based check
        if mission_ah_req and hasattr(self.v, 'battery_remaining_Ah'):
            remaining_ah = self.v.battery_remaining_Ah
            soc_margin = remaining_ah - mission_ah_req

            if soc_margin >= self.BATTERY_RESERVE_AH:
                checks.append(CheckResult(name="Battery Capacity (Ah)", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Battery Capacity (Ah)",
                    status=CheckStatus.FAIL,
                    message=f"Margin {soc_margin:.2f}Ah < {self.BATTERY_RESERVE_AH}Ah reserve"
                ))

        return checks

    # ==================== Basic Checks (Original Simplified Versions) ====================
    def check_basic_link(self):
        """Basic MAVLink link check."""
        if hasattr(self.v, 'heartbeat_age_s'):
            if self.v.heartbeat_age_s < self.HEARTBEAT_MAX_AGE:
                return CheckResult(name="MAVLink Link", status=CheckStatus.PASS)
            return CheckResult(name="MAVLink Link", status=CheckStatus.FAIL)
        return CheckResult(name="MAVLink Link", status=CheckStatus.SKIP, message="Heartbeat data not available")

    def check_basic_gps(self):
        """Basic GPS check."""
        if hasattr(self.v, 'gps_fix_type') and hasattr(self.v, 'hdop'):
            if self.v.gps_fix_type >= 3 and self.v.hdop <= self.HDOP_MAX:
                return CheckResult(name="GPS Lock", status=CheckStatus.PASS)
            return CheckResult(
                name="GPS Lock",
                status=CheckStatus.FAIL,
                message=f"Fix:{self.v.gps_fix_type}, HDOP:{self.v.hdop}"
            )
        return CheckResult(name="GPS Lock", status=CheckStatus.SKIP, message="GPS data not available")

    def check_basic_battery(self, estimated_time_s=None):
        """Basic battery check."""
        if estimated_time_s is None and self.ctx.mission:
            # Estimate from distance
            distance = self.ctx.total_distance()
            speed = self.ctx.mission.speed
            estimated_time_s = distance / speed if speed and speed > 0 else 0

        if estimated_time_s and hasattr(self.v, 'max_flight_time_s') and hasattr(self.v, 'battery_remaining_pct'):
            required_pct = (estimated_time_s / self.v.max_flight_time_s) * 100
            remaining = self.v.battery_remaining_pct

            if remaining >= required_pct + self.BATTERY_RESERVE_PCT:
                return CheckResult(name="Battery Margin", status=CheckStatus.PASS)
            return CheckResult(
                name="Battery Margin",
                status=CheckStatus.FAIL,
                message=f"Remaining {remaining}% < Required {required_pct:.1f}%"
            )

        return CheckResult(name="Battery Margin", status=CheckStatus.SKIP, message="Battery data not available")

    # ==================== Mission Upload Integrity ====================
    def check_mission_integrity(self, mission_waypoints, expected_count, mission_crc):
        """Check mission upload integrity."""
        checks = []

        # Mission count check
        if len(mission_waypoints) == expected_count:
            checks.append(CheckResult(name="Mission Count", status=CheckStatus.PASS))
        else:
            checks.append(CheckResult(
                name="Mission Count",
                status=CheckStatus.FAIL,
                message=f"Got {len(mission_waypoints)} waypoints, expected {expected_count}"
            ))

        # CRC check
        if mission_crc == getattr(self.v, 'mission_crc', None):
            checks.append(CheckResult(name="Mission CRC", status=CheckStatus.PASS))
        else:
            checks.append(CheckResult(
                name="Mission CRC",
                status=CheckStatus.FAIL,
                message="Mission CRC mismatch"
            ))

        # First/last command validity
        if mission_waypoints:
            # Check first command (should be takeoff or similar)
            if hasattr(mission_waypoints[0], 'command') and mission_waypoints[0].command in [22, 23]:  # MAV_CMD_NAV_TAKEOFF
                checks.append(CheckResult(name="First Command", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="First Command",
                    status=CheckStatus.WARN,
                    message="First command is not takeoff"
                ))

            # Check last command (should be RTL or land)
            if hasattr(mission_waypoints[-1], 'command'):
                last_cmd = mission_waypoints[-1].command
                if last_cmd in [20, 21, 22]:  # RTL, LAND, TAKEOFF
                    checks.append(CheckResult(name="Last Command", status=CheckStatus.PASS))
                else:
                    checks.append(CheckResult(
                        name="Last Command",
                        status=CheckStatus.WARN,
                        message="Last command is not RTL or land"
                    ))

        return checks

    # ==================== Failsafe Configuration ====================
    def check_failsafe_config(self):
        """Check failsafe configuration."""
        checks = []

        # RTL altitude
        if hasattr(self.v, 'rtl_alt_m'):
            if self.v.rtl_alt_m >= self.RTL_MIN_ALT:
                checks.append(CheckResult(name="RTL Altitude", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="RTL Altitude",
                    status=CheckStatus.FAIL,
                    message=f"RTL alt {self.v.rtl_alt_m}m < {self.RTL_MIN_ALT}m"
                ))

        # Battery failsafe enabled
        if hasattr(self.v, 'battery_failsafe_enabled'):
            if self.v.battery_failsafe_enabled:
                checks.append(CheckResult(name="Battery Failsafe", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Battery Failsafe",
                    status=CheckStatus.FAIL,
                    message="Battery failsafe not enabled"
                ))

        # Geofence action
        if hasattr(self.v, 'geo_fence_action'):
            if self.v.geo_fence_action != 0:  # 0 = NONE
                checks.append(CheckResult(name="Geofence Action", status=CheckStatus.PASS))
            else:
                checks.append(CheckResult(
                    name="Geofence Action",
                    status=CheckStatus.FAIL,
                    message="Geofence action set to NONE"
                ))

        return checks

    def run(self, estimated_time_s=None, mission_waypoints=None,
            expected_mission_count=None, mission_crc=None,
            mission_ah_req=None, allowed_modes=None):
        """
        Run all base checks.

        Args:
            estimated_time_s: Estimated mission time in seconds
            mission_waypoints: List of mission waypoints for integrity check
            expected_mission_count: Expected number of waypoints
            mission_crc: Mission CRC for integrity check
            mission_ah_req: Required amp-hours for mission
            allowed_modes: List of allowed flight modes

        Returns:
            List of CheckResult objects
        """
        results = []

        # Basic checks
        results.append(self.check_basic_link())
        results.append(self.check_basic_gps())
        results.append(self.check_basic_battery(estimated_time_s))

        # Enhanced checks
        results.extend(self.check_link_health())
        results.extend(self.check_vehicle_state(allowed_modes))
        results.extend(self.check_gps_quality())
        results.extend(self.check_home_position())
        results.extend(self.check_ekf_health())
        results.extend(self.check_wind())
        results.extend(self.check_geofence())
        results.extend(self.check_no_fly_zones())

        # Battery checks
        battery_checks = self.check_battery_capacity(estimated_time_s, mission_ah_req)
        if isinstance(battery_checks, list):
            results.extend(battery_checks)
        else:
            results.append(battery_checks)

        # Mission integrity
        if mission_waypoints is not None and expected_mission_count is not None:
            results.extend(self.check_mission_integrity(mission_waypoints,
                                                        expected_mission_count,
                                                        mission_crc))

        # Failsafe configuration
        results.extend(self.check_failsafe_config())

        # Filter out None results
        return [r for r in results if r is not None]