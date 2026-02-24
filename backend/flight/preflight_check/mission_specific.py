from .schemas import CheckResult, CheckStatus
from math import tan, radians, atan, sqrt, pi, sin, cos
from typing import List, Optional, Any, Dict
from ..missions.schemas import (
    Mission, GridMission, OrbitMission, TerrainFollowMission,
    PerimeterPatrolMission, AdaptiveAltitudeMission, Waypoint
)
from .preflight_context import PreflightContext
import math


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

    def run(self) -> List[CheckResult]:
        """Base run method to be overridden."""
        return []


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

    def run(self) -> List[CheckResult]:
        """Run all grid mission checks."""
        results = []
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

    def run(self) -> List[CheckResult]:
        """Run all terrain-following mission checks."""
        return self.check_terrain_follow_feasibility()


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

    def run(self) -> List[CheckResult]:
        """Run all orbit mission checks."""
        results = []
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

    def run(self) -> List[CheckResult]:
        """Run all perimeter patrol checks."""
        results = []
        results.append(self.check_polygon_validity())
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

    def run(self) -> List[CheckResult]:
        """Run all adaptive altitude checks."""
        results = []
        results.extend(self.check_altitude_limits())
        results.append(self.check_agl_envelope())
        return results


# Factory function to create appropriate mission preflight instance
def create_mission_preflight(context: PreflightContext) -> MissionPreflightBase:
    """
    Factory function to create the appropriate mission preflight instance.

    Args:
        context: PreflightContext containing mission and vehicle state

    Returns:
        Appropriate MissionPreflightBase subclass instance
    """
    mission_type = context.mission.type.lower() if hasattr(context.mission, 'type') else ""

    mission_classes = {
        'grid': GridMissionPreflight,
        'survey': GridMissionPreflight,
        'terrain_follow': TerrainFollowMissionPreflight,
        'orbit': OrbitMissionPreflight,
        'circle': OrbitMissionPreflight,
        'poi': OrbitMissionPreflight,
        'perimeter_patrol': PerimeterPatrolMissionPreflight,
        'polygon': PerimeterPatrolMissionPreflight,
        'patrol': PerimeterPatrolMissionPreflight,
        'adaptive_altitude': AdaptiveAltitudeMissionPreflight,
    }

    # Handle aliases
    base_type = mission_type
    if mission_type in ['survey']:
        base_type = 'grid'
    elif mission_type in ['circle', 'poi']:
        base_type = 'orbit'
    elif mission_type in ['polygon', 'patrol']:
        base_type = 'perimeter_patrol'

    mission_class = mission_classes.get(base_type) or mission_classes.get(mission_type)

    if mission_class:
        return mission_class(context)
    else:
        # Return base class that does nothing
        return MissionPreflightBase(context)