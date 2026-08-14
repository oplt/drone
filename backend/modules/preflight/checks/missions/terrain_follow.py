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
        return await self._run_independent_checks(
            self.check_waypoint_count_limit,
            self.check_speed_limits,
            self.check_max_range_from_home,
            self.check_geofence_containment,
            self.check_no_fly_zones,
            self.check_terrain_follow_feasibility,
        )


