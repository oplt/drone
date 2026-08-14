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


