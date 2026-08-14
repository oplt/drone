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

class WaypointMissionPreflight(MissionPreflightBase):
    """Generic waypoint-route mission (non-grid/orbit/patrol) checks."""

    async def run(self) -> list[CheckResult]:
        return await self._run_independent_checks(
            self.check_waypoint_count_limit,
            self.check_speed_limits,
            self.check_max_range_from_home,
            self.check_geofence_containment,
            self.check_no_fly_zones,
            self.check_basic_terrain_clearance,
            self.check_preflight_range,
        )


