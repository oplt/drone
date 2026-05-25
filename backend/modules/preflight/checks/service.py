import logging
import time
from typing import Any

from backend.modules.missions.schemas.mission_types import Mission, create_mission_from_dict

from .base import BasePreflightChecks
from .cache import TerrainCache
from .check_models import MissionDataPreprocessor
from .context import PreflightContext
from .indoor_warehouse import IndoorWarehouseBasePreflightChecks
from .mission_specific import create_mission_preflight
from .profiles import (
    INDOOR_WAREHOUSE_CRITICAL_BASE_CHECKS,
    INDOOR_WAREHOUSE_CRITICAL_MISSION_CHECKS,
    indoor_warehouse_overrides,
)
from .schemas import CheckResult, CheckStatus, PreflightReport

logger = logging.getLogger(__name__)

CRITICAL_BASE_CHECKS = [
    "MAVLink Link",
    "GPS Lock",
    "Heartbeat Age",
    "GPS Fix Type",
    "Vehicle Armable",
    "EKF Health",
]

CRITICAL_MISSION_CHECKS = [
    "Grid Camera Footprint",
    "Orbit Bank Angle",
    "Orbit Lateral Acceleration",
    "Cornering Limits",
    "Warehouse Local Position",
    "Warehouse Corridors",
    "Warehouse Scan Layers",
    "Warehouse Keepouts",
]


class PreflightOrchestrator:
    """Orchestrates all preflight checks."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        self.terrain_cache = TerrainCache(
            precision=self.config.get("terrain_cache_precision", 1e-5),
            ttl_seconds=self.config.get("terrain_cache_ttl", 300),
        )

        self.critical_base_checks = self.config.get("critical_base_checks", CRITICAL_BASE_CHECKS)
        self.critical_mission_checks = self.config.get(
            "critical_mission_checks", CRITICAL_MISSION_CHECKS
        )
        self.early_terminate_on_fail = self.config.get("early_terminate_on_fail", True)

    async def _build_context(
        self, vehicle_state: Any, mission: Mission, **kwargs
    ) -> PreflightContext:
        precomputed = None
        if mission.waypoints:
            preprocessor = MissionDataPreprocessor(terrain_cache=self.terrain_cache)
            precomputed = await preprocessor.preprocess(
                mission.waypoints, terrain_data=kwargs.get("terrain_provider")
            )

        return PreflightContext(
            vehicle_state=vehicle_state,
            mission=mission,
            precomputed=precomputed,
            terrain_cache=self.terrain_cache,
            **{
                k: kwargs.get(k)
                for k in [
                    "terrain_provider",
                    "wind_data",
                    "no_fly_zones",
                    "obstacle_map",
                    "geofence_polygon",
                    "config_overrides",
                    "vehicle_id",
                    "flight_id",
                ]
            },
        )

    def _check_for_critical_fails(
        self, results: list[CheckResult], check_type: str = "base"
    ) -> tuple[bool, list[CheckResult]]:
        critical_list = (
            self.critical_base_checks if check_type == "base" else self.critical_mission_checks
        )
        failed_critical = [
            r for r in results if r.name in critical_list and r.status == CheckStatus.FAIL
        ]
        return len(failed_critical) > 0, failed_critical

    def _determine_overall_status(self, results: list[CheckResult]) -> CheckStatus:
        has_fail = any(r.status == CheckStatus.FAIL for r in results)
        has_warn = any(r.status == CheckStatus.WARN for r in results)
        if has_fail:
            return CheckStatus.FAIL
        if has_warn:
            return CheckStatus.WARN
        return CheckStatus.PASS

    def _generate_summary(self, results: list[CheckResult]) -> dict[str, Any]:
        return {
            "total_checks": len(results),
            "passed": sum(1 for r in results if r.status == CheckStatus.PASS),
            "failed": sum(1 for r in results if r.status == CheckStatus.FAIL),
            "warned": sum(1 for r in results if r.status == CheckStatus.WARN),
            "skipped": sum(1 for r in results if r.status == CheckStatus.SKIP),
        }

    async def run(
        self, vehicle_state: Any, mission_data: dict | Mission, **kwargs
    ) -> PreflightReport:
        # Validate mission
        mission = (
            create_mission_from_dict(mission_data)
            if isinstance(mission_data, dict)
            else mission_data
        )

        # ✅ Warehouse-scan overrides (indoors)
        mission_type = getattr(mission, "type", "") or ""
        mission_type = str(mission_type).lower()

        overrides = dict(kwargs.get("config_overrides") or {})
        gps_timeout_s = float(kwargs.get("gps_timeout_s") or 30.0)

        if mission_type == "warehouse_scan":
            # Relax GNSS gates; allow indoor operation.
            overrides.update(
                {
                    "GPS_FIX_TYPE_MIN": 0,
                    "SAT_MIN": 0,
                    "HDOP_MAX": 99.0,
                    # Indoor typically short: keep range enforcement soft
                    "ENFORCE_PREFLIGHT_RANGE": False,
                    "HOME_POSITION_REQUIRED": False,
                    # Make preflight faster
                    "HEARTBEAT_MAX_AGE": overrides.get("HEARTBEAT_MAX_AGE", 3.0),
                    "MAX_WAYPOINTS": overrides.get("MAX_WAYPOINTS", 2500),
                    "WAREHOUSE_ODOMETRY_DRIFT_MAX_M": overrides.get(
                        "WAREHOUSE_ODOMETRY_DRIFT_MAX_M",
                        0.75,
                    ),
                }
            )
            gps_timeout_s = float(kwargs.get("gps_timeout_s") or 3.0)
        elif mission_type == "indoor_exploration":
            overrides.update(indoor_warehouse_overrides())
            self.critical_base_checks = INDOOR_WAREHOUSE_CRITICAL_BASE_CHECKS
            self.critical_mission_checks = INDOOR_WAREHOUSE_CRITICAL_MISSION_CHECKS
            gps_timeout_s = 0.0

        kwargs["config_overrides"] = overrides

        # Build context (fetches terrain concurrently)
        context = await self._build_context(vehicle_state, mission, **kwargs)

        # Calculate estimated time
        total_distance = context.total_distance()
        speed = getattr(mission, "speed", None) or 10
        estimated_time_s = (
            kwargs.get("estimated_time_s")
            or getattr(mission, "max_mission_time_s", None)
            or (total_distance / speed)
        )

        # Run base checks
        base_checker = (
            IndoorWarehouseBasePreflightChecks(context)
            if mission_type == "indoor_exploration"
            else BasePreflightChecks(context)
        )
        base_results = await base_checker.run(
            estimated_time_s=estimated_time_s,
            mission_waypoints=mission.waypoints,
            expected_mission_count=len(mission.waypoints),
            mission_crc=kwargs.get("mission_crc"),
            gps_timeout_s=gps_timeout_s,
            fail_fast=self.early_terminate_on_fail,
        )

        has_critical_fail, failed_critical = self._check_for_critical_fails(base_results, "base")
        if has_critical_fail and self.early_terminate_on_fail:
            overall = self._determine_overall_status(base_results)
            return PreflightReport(
                mission_type=mission_type,
                overall_status=overall,
                base_checks=base_results,
                mission_checks=[],
                critical_failures=failed_critical,
                summary=self._generate_summary(base_results),
                timestamp=time.time(),
                vehicle_id=kwargs.get("vehicle_id"),
            )

        # Run mission-specific checks
        mission_checker = create_mission_preflight(context)
        mission_results = await mission_checker.run()

        all_results = base_results + mission_results
        overall_status = self._determine_overall_status(all_results)

        critical_fail2, failed_critical2 = self._check_for_critical_fails(
            mission_results, "mission"
        )

        return PreflightReport(
            mission_type=mission_type,
            overall_status=overall_status,
            base_checks=base_results,
            mission_checks=mission_results,
            critical_failures=(failed_critical2 if critical_fail2 else None),
            summary=self._generate_summary(all_results),
            timestamp=time.time(),
            vehicle_id=kwargs.get("vehicle_id"),
        )
