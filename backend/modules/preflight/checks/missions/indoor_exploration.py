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

class IndoorExplorationMissionPreflight(MissionPreflightBase):
    """Mission-parameter checks for indoor frontier exploration."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: IndoorExplorationMission = context.mission

    def check_mission_parameters(self) -> CheckResult:
        if float(self.mission.max_mission_time_s) <= 0:
            return CheckResult(
                name="Indoor Mission Parameters",
                status=CheckStatus.FAIL,
                message="max_mission_time_s must be positive",
            )
        if float(self.mission.max_exploration_radius_m) <= float(
            self.mission.safe_takeoff_bubble_radius_m
        ):
            return CheckResult(
                name="Indoor Mission Parameters",
                status=CheckStatus.FAIL,
                message="max_exploration_radius_m must exceed the dock takeoff bubble",
            )
        if float(self.mission.max_path_length_m) <= float(self.mission.max_exploration_radius_m):
            return CheckResult(
                name="Indoor Mission Parameters",
                status=CheckStatus.FAIL,
                message="max_path_length_m must exceed max_exploration_radius_m",
            )
        if float(self.mission.occupancy_resolution_m) > float(
            self.mission.minimum_corridor_clearance_m
        ):
            return CheckResult(
                name="Indoor Mission Parameters",
                status=CheckStatus.FAIL,
                message="occupancy_resolution_m is too coarse for the corridor clearance constraint",
            )
        return CheckResult(
            name="Indoor Mission Parameters",
            status=CheckStatus.PASS,
            message="Indoor exploration limits are internally consistent",
        )

    def check_frame_config(self) -> CheckResult:
        dock = self.mission.dock
        frames = {
            dock.pose.frame_id,
            dock.entry_pose.frame_id,
            dock.exit_pose.frame_id,
            getattr(self.mission, "local_control_mode", "local_setpoint"),
        }
        if (
            dock.pose.frame_id != "map"
            or dock.entry_pose.frame_id != "map"
            or dock.exit_pose.frame_id != "map"
        ):
            return CheckResult(
                name="Indoor Frames",
                status=CheckStatus.FAIL,
                message="Dock, entry, and exit poses must be declared in the map frame",
            )
        if "local_setpoint" not in frames:
            return CheckResult(
                name="Indoor Frames",
                status=CheckStatus.FAIL,
                message="Indoor exploration requires local_setpoint control mode",
            )
        return CheckResult(
            name="Indoor Frames",
            status=CheckStatus.PASS,
            message="Dock, map, and local-control frames are configured",
        )

    def check_dock_geometry(self) -> CheckResult:
        dock = self.mission.dock
        entry_distance = math.hypot(
            float(dock.entry_pose.x_m) - float(dock.pose.x_m),
            float(dock.entry_pose.y_m) - float(dock.pose.y_m),
        )
        exit_distance = math.hypot(
            float(dock.exit_pose.x_m) - float(dock.pose.x_m),
            float(dock.exit_pose.y_m) - float(dock.pose.y_m),
        )
        if entry_distance > float(self.mission.dock_search_radius_m) * 4.0:
            return CheckResult(
                name="Indoor Dock Geometry",
                status=CheckStatus.FAIL,
                message="Dock entry pose is too far from the dock anchor",
            )
        if exit_distance > float(self.mission.max_exploration_radius_m):
            return CheckResult(
                name="Indoor Dock Geometry",
                status=CheckStatus.FAIL,
                message="Dock exit pose exceeds the maximum exploration radius",
            )
        return CheckResult(
            name="Indoor Dock Geometry",
            status=CheckStatus.PASS,
            message=(f"Dock entry {entry_distance:.1f}m, exit {exit_distance:.1f}m from dock"),
        )

    def check_return_reserve(self) -> CheckResult:
        if float(self.mission.battery_return_reserve_pct) <= float(
            self.mission.battery_emergency_land_reserve_pct
        ):
            return CheckResult(
                name="Indoor Return Reserve",
                status=CheckStatus.FAIL,
                message="Return reserve must exceed emergency land reserve",
            )
        return CheckResult(
            name="Indoor Return Reserve",
            status=CheckStatus.PASS,
            message=(
                f"Return reserve {float(self.mission.battery_return_reserve_pct):.1f}% > "
                f"emergency reserve {float(self.mission.battery_emergency_land_reserve_pct):.1f}%"
            ),
        )

    def check_localization_thresholds(self) -> CheckResult:
        if float(self.mission.localization_confidence_return_threshold) > float(
            self.mission.localization_confidence_min
        ):
            return CheckResult(
                name="Indoor Localization Thresholds",
                status=CheckStatus.FAIL,
                message="Return threshold must not exceed the continue-flight confidence threshold",
            )
        return CheckResult(
            name="Indoor Localization Thresholds",
            status=CheckStatus.PASS,
            message=(
                f"continue={float(self.mission.localization_confidence_min):.2f}, "
                f"return={float(self.mission.localization_confidence_return_threshold):.2f}"
            ),
        )

    async def run(self) -> list[CheckResult]:
        return [
            self.check_speed_limits(),
            self.check_mission_parameters(),
            self.check_frame_config(),
            self.check_dock_geometry(),
            self.check_return_reserve(),
            self.check_localization_thresholds(),
        ]


def create_mission_preflight(context: PreflightContext) -> MissionPreflightBase:
    mission_type = str(getattr(context.mission, "type", "") or "").lower()

    aliases = {
        "survey": "grid",
        "circle": "orbit",
        "poi": "orbit",
        "private_patrol": "perimeter_patrol",
        "polygon": "perimeter_patrol",
        "patrol": "perimeter_patrol",
    }

    mission_type = aliases.get(mission_type, mission_type)

    mission_classes: dict[str, type[MissionPreflightBase]] = {
        "grid": GridMissionPreflight,
        "warehouse_scan": WarehouseScanMissionPreflight,
        "indoor_exploration": IndoorExplorationMissionPreflight,
        "terrain_follow": TerrainFollowMissionPreflight,
        "orbit": OrbitMissionPreflight,
        "perimeter_patrol": PerimeterPatrolMissionPreflight,
        "adaptive_altitude": AdaptiveAltitudeMissionPreflight,
        "route": WaypointMissionPreflight,
    }

    return mission_classes.get(mission_type, WaypointMissionPreflight)(context)
