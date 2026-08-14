from __future__ import annotations

import asyncio
import math
from collections.abc import Iterable, Sequence
from math import atan, pi, radians, tan
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from backend.core.config.runtime import env_truthy, settings
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

from ..context import PreflightContext
from ..schemas import CheckResult, CheckStatus
from .base import MissionPreflightBase, warehouse_sim_mode

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
        return await self._run_independent_checks(
            self.check_polygon_validity,
            self.check_speed_limits,
            self.check_agl_envelope_basic,
            self.check_max_range_from_home,
            self.check_geofence_containment,
            self.check_no_fly_zones,
            self.check_boundary_buffer,
            self.check_cornering_limits,
        )


