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

class GridMissionPreflight(MissionPreflightBase):
    """Grid/Survey mission preflight checks."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        # Type cast for IDE support
        self.mission: GridMission = context.mission

    def check_camera_footprint(self) -> CheckResult:
        """Check if line spacing is compatible with camera footprint."""
        if not hasattr(self.mission, "camera") or not self.mission.camera:
            return CheckResult(
                name="Grid Camera Footprint",
                status=CheckStatus.SKIP,
                message="No camera specifications provided",
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
                message="; ".join(issues),
            )

        return CheckResult(
            name="Grid Camera Footprint",
            status=CheckStatus.PASS,
            message=f"Footprint: {footprint_width_m:.1f}×{footprint_height_m:.1f}m",
        )

    def check_mission_duration(self) -> CheckResult:
        """Check if mission duration is within vehicle limits."""
        total_distance = self.ctx.total_distance()
        flight_time_s = total_distance / self.mission.speed if self.mission.speed > 0 else 0

        # Add turn penalties
        if hasattr(self.mission, "grid_segments") and self.mission.grid_segments:
            num_turns = len(self.mission.grid_segments) - 1
            flight_time_s += self.TURN_PENALTY_S * num_turns

        if hasattr(self.v, "max_flight_time_s") and self.v.max_flight_time_s:
            if flight_time_s > self.v.max_flight_time_s:
                return CheckResult(
                    name="Grid Duration",
                    status=CheckStatus.FAIL,
                    message=f"Est. time {flight_time_s / 60:.1f}min > "
                    f"max {self.v.max_flight_time_s / 60:.1f}min",
                )

        return CheckResult(
            name="Grid Duration",
            status=CheckStatus.PASS,
            message=f"Est. time: {flight_time_s / 60:.1f}min",
        )

    async def run(self) -> list[CheckResult]:
        """Run all grid mission checks."""
        return await self._run_independent_checks(
            self.check_waypoint_count_limit,
            self.check_speed_limits,
            self.check_agl_envelope_basic,
            self.check_max_range_from_home,
            self.check_geofence_containment,
            self.check_no_fly_zones,
            self.check_basic_terrain_clearance,
            self.check_grid_turn_margin,
            self.check_camera_footprint,
            self.check_mission_duration,
        )


