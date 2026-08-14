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

class OrbitMissionPreflight(MissionPreflightBase):
    """Orbit / POI mission preflight checks."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: OrbitMission = context.mission

    def check_turn_feasibility(self) -> list[CheckResult]:
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
            results.append(
                CheckResult(
                    name="Orbit Bank Angle",
                    status=CheckStatus.PASS,
                    message=f"Bank: {bank_deg:.1f}° (max {self.BANK_MAX_DEG}°)",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Orbit Bank Angle",
                    status=CheckStatus.FAIL,
                    message=f"Bank angle {bank_deg:.1f}° > {self.BANK_MAX_DEG}°",
                )
            )

        # Lateral acceleration check
        if a_lat <= self.A_LAT_MAX:
            results.append(
                CheckResult(
                    name="Orbit Lateral Acceleration",
                    status=CheckStatus.PASS,
                    message=f"Lateral accel: {a_lat:.2f}m/s² (max {self.A_LAT_MAX}m/s²)",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Orbit Lateral Acceleration",
                    status=CheckStatus.FAIL,
                    message=f"Lateral accel {a_lat:.2f}m/s² > {self.A_LAT_MAX}m/s²",
                )
            )

        return results

    def check_clearance(self) -> CheckResult:
        """Check clearance around POI."""
        # Check minimum standoff
        if self.mission.radius < self.mission.min_standoff_m:
            return CheckResult(
                name="POI Clearance",
                status=CheckStatus.FAIL,
                message=f"Orbit radius {self.mission.radius}m < min standoff {self.mission.min_standoff_m}m",
            )

        # Check AGL if POI location has terrain
        if self.mission.poi_location:
            agl = self.mission.altitude_agl
            if agl < self.AGL_MIN or agl > self.AGL_MAX:
                return CheckResult(
                    name="Orbit AGL",
                    status=CheckStatus.WARN,
                    message=f"Orbit AGL {agl}m may be outside safe envelope ({self.AGL_MIN}-{self.AGL_MAX}m)",
                )

        return CheckResult(
            name="POI Clearance",
            status=CheckStatus.PASS,
            message=f"Radius: {self.mission.radius}m, Standoff OK",
        )

    async def run(self) -> list[CheckResult]:
        """Run all orbit mission checks."""
        return await self._run_independent_checks(
            self.check_speed_limits,
            self.check_max_range_from_home,
            self.check_geofence_containment,
            self.check_no_fly_zones,
            self.check_turn_feasibility,
            self.check_clearance,
        )


