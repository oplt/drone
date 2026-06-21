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
    WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS,
    WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS,
    indoor_warehouse_overrides,
    warehouse_scan_preflight_overrides,
)
from .schemas import CheckResult, CheckStatus, PreflightReport
from .warehouse_scan_base import WarehouseRosBasePreflightChecks

logger = logging.getLogger(__name__)

CRITICAL_BASE_CHECKS = [
    "Link Health",
    "Heartbeat Age",
    "Message Rate",
    "GPS Fix Type",
    "Vehicle Armable",
    "Flight Mode",
    "Arming Checks",
    "EKF Health",
    "Battery Voltage",
    "Battery Budget (%)",
    "Battery Budget (Ah)",
]

CRITICAL_MISSION_CHECKS = [
    "Grid Camera Footprint",
    "Orbit Bank Angle",
    "Orbit Lateral Acceleration",
    "Cornering Limits",
    "Warehouse Local Position",
    "Warehouse ROS Bridge",
    "Warehouse Camera Topics",
    "Warehouse Stereo Sync",
    "Warehouse IMU Topic",
    "Warehouse TF Tree",
    "Warehouse Visual SLAM",
    "Warehouse Nvblox",
    "Warehouse Mapping Disk",
    "Warehouse Sensor Rig",
    "Warehouse Battery Margin",
    "Warehouse Dock Marker",
    "Warehouse Corridors",
    "Warehouse Scan Layers",
    "Warehouse Keepouts",
    "Indoor Mission Parameters",
    "Indoor Frames",
    "Indoor Dock Geometry",
    "Indoor Return Reserve",
    "Indoor Localization Thresholds",
]


def _unique(items: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(items))


class PreflightOrchestrator:
    """Runs base and mission-specific preflight checks without mutating request-specific state."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        self.terrain_cache = TerrainCache(
            precision=float(self.config.get("terrain_cache_precision", 1e-5)),
            ttl_seconds=self.config.get("terrain_cache_ttl", 300),
        )

        self.preprocessor = MissionDataPreprocessor(terrain_cache=self.terrain_cache)

        self.default_critical_base_checks = list(
            self.config.get("critical_base_checks", CRITICAL_BASE_CHECKS)
        )
        self.default_critical_mission_checks = list(
            self.config.get("critical_mission_checks", CRITICAL_MISSION_CHECKS)
        )

        self.early_terminate_on_fail = bool(self.config.get("early_terminate_on_fail", True))

    @staticmethod
    def _mission_type(mission: Mission) -> str:
        return str(getattr(mission, "type", "") or "").lower()

    def _profile(
            self,
            mission_type: str,
            overrides: dict[str, Any],
            gps_timeout_s: float,
    ) -> tuple[type[BasePreflightChecks], dict[str, Any], list[str], list[str], float]:
        base_checker_cls: type[BasePreflightChecks] = BasePreflightChecks
        critical_base = list(self.default_critical_base_checks)
        critical_mission = list(self.default_critical_mission_checks)

        if mission_type == "warehouse_scan":
            merged = warehouse_scan_preflight_overrides()
            merged.update(overrides)
            overrides = merged

            base_checker_cls = WarehouseRosBasePreflightChecks
            critical_base = _unique(
                list(WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS)
                + ["Warehouse ROS Position", "Warehouse ROS Odometry"]
            )
            critical_mission = _unique(list(WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS))
            gps_timeout_s = 0.0

        elif mission_type == "indoor_exploration":
            merged = indoor_warehouse_overrides()
            merged.update(overrides)
            overrides = merged

            base_checker_cls = IndoorWarehouseBasePreflightChecks
            critical_base = _unique(list(INDOOR_WAREHOUSE_CRITICAL_BASE_CHECKS))
            critical_mission = _unique(list(INDOOR_WAREHOUSE_CRITICAL_MISSION_CHECKS))
            gps_timeout_s = 0.0

        return base_checker_cls, overrides, critical_base, critical_mission, gps_timeout_s

    async def _build_context(
            self,
            vehicle_state: Any,
            mission: Mission,
            *,
            overrides: dict[str, Any],
            **kwargs: Any,
    ) -> PreflightContext:
        waypoints = list(getattr(mission, "waypoints", []) or [])

        precomputed = None
        if waypoints:
            precomputed = await self.preprocessor.preprocess(
                waypoints,
                terrain_data=kwargs.get("terrain_provider"),
            )

        return PreflightContext(
            vehicle_state=vehicle_state,
            mission=mission,
            precomputed=precomputed,
            terrain_cache=self.terrain_cache,
            distance_cache=self.preprocessor.distance_cache,
            terrain_provider=kwargs.get("terrain_provider"),
            wind_data=kwargs.get("wind_data"),
            weather_data=kwargs.get("weather_data"),
            weather_api_error=kwargs.get("weather_api_error"),
            no_fly_zones=kwargs.get("no_fly_zones"),
            obstacle_map=kwargs.get("obstacle_map"),
            geofence_polygon=kwargs.get("geofence_polygon"),
            config_overrides=overrides,
            vehicle_id=kwargs.get("vehicle_id"),
            flight_id=kwargs.get("flight_id"),
        )

    @staticmethod
    def _critical_fails(
            results: list[CheckResult],
            critical_names: list[str],
    ) -> list[CheckResult]:
        critical = set(critical_names)
        return [r for r in results if r.name in critical and r.status == CheckStatus.FAIL]

    @staticmethod
    def _determine_overall_status(results: list[CheckResult]) -> CheckStatus:
        if any(r.status == CheckStatus.FAIL for r in results):
            return CheckStatus.FAIL
        if any(r.status == CheckStatus.WARN for r in results):
            return CheckStatus.WARN
        return CheckStatus.PASS

    def _warehouse_overall_status(
            self,
            mission_type: str,
            results: list[CheckResult],
            critical_base: list[str],
            critical_mission: list[str],
    ) -> CheckStatus:
        if mission_type not in {"warehouse_scan", "indoor_exploration"}:
            return self._determine_overall_status(results)

        critical_names = set(critical_base) | set(critical_mission)
        critical_results = [r for r in results if r.name in critical_names]

        if any(r.status == CheckStatus.FAIL for r in critical_results):
            return CheckStatus.FAIL
        if any(r.status in {CheckStatus.FAIL, CheckStatus.WARN} for r in results):
            return CheckStatus.WARN
        return CheckStatus.PASS

    @staticmethod
    def _summary(results: list[CheckResult]) -> dict[str, Any]:
        return {
            "total_checks": len(results),
            "passed": sum(1 for r in results if r.status == CheckStatus.PASS),
            "failed": sum(1 for r in results if r.status == CheckStatus.FAIL),
            "warned": sum(1 for r in results if r.status == CheckStatus.WARN),
            "skipped": sum(1 for r in results if r.status == CheckStatus.SKIP),
        }

    async def run(
            self,
            vehicle_state: Any,
            mission_data: dict | Mission,
            **kwargs: Any,
    ) -> PreflightReport:
        mission = create_mission_from_dict(mission_data) if isinstance(mission_data, dict) else mission_data
        mission_type = self._mission_type(mission)

        overrides = dict(kwargs.get("config_overrides") or {})
        gps_timeout_s = float(
            kwargs.get("gps_timeout_s", self.config.get("gps_timeout_s", 0.0)) or 0.0
        )

        base_cls, overrides, critical_base, critical_mission, gps_timeout_s = self._profile(
            mission_type,
            overrides,
            gps_timeout_s,
        )

        weather_data = kwargs.get("weather_data")
        wind_data = kwargs.get("wind_data")
        weather_api_error = kwargs.get("weather_api_error")
        if (
            weather_data is None
            and wind_data is None
            and weather_api_error is None
        ):
            from backend.modules.preflight.weather.location import (
                is_outdoor_preflight_mission,
                resolve_preflight_coordinates,
            )
            from backend.modules.preflight.weather.service import fetch_weather_for_preflight

            if is_outdoor_preflight_mission(mission_type):
                coords = resolve_preflight_coordinates(
                    vehicle_state,
                    mission,
                    geofence_polygon=kwargs.get("geofence_polygon"),
                )
                if coords is None:
                    weather_api_error = "GPS coordinates unavailable for weather lookup"
                else:
                    snapshot, fetch_error = await fetch_weather_for_preflight(
                        coords[0],
                        coords[1],
                        config=overrides,
                    )
                    if snapshot is not None:
                        weather_data = snapshot.to_dict()
                        wind_data = snapshot.wind_data_dict()
                    else:
                        weather_api_error = fetch_error or "Weather API unavailable"

        context = await self._build_context(
            vehicle_state,
            mission,
            overrides=overrides,
            weather_data=weather_data,
            wind_data=wind_data,
            weather_api_error=weather_api_error,
            **kwargs,
        )

        waypoints = list(getattr(mission, "waypoints", []) or [])
        speed = float(getattr(mission, "speed", None) or 10.0)
        total_distance = context.total_distance()

        estimated_time_s = (
                kwargs.get("estimated_time_s")
                or getattr(mission, "max_mission_time_s", None)
                or (total_distance / speed if speed > 0 else None)
        )

        base_results = await base_cls(context).run(
            estimated_time_s=estimated_time_s,
            mission_waypoints=waypoints,
            expected_mission_count=len(waypoints),
            mission_crc=kwargs.get("mission_crc"),
            gps_timeout_s=gps_timeout_s,
            fail_fast=self.early_terminate_on_fail,
        )

        base_critical_failures = self._critical_fails(base_results, critical_base)

        if base_critical_failures and self.early_terminate_on_fail:
            return PreflightReport(
                mission_type=mission_type,
                overall_status=self._determine_overall_status(base_results),
                base_checks=base_results,
                mission_checks=[],
                mission_checks_skipped=True,
                critical_failures=base_critical_failures,
                summary=self._summary(base_results),
                timestamp=time.time(),
                vehicle_id=kwargs.get("vehicle_id"),
            )

        mission_results = await create_mission_preflight(context).run()
        mission_critical_failures = self._critical_fails(mission_results, critical_mission)
        all_results = base_results + mission_results

        return PreflightReport(
            mission_type=mission_type,
            overall_status=self._warehouse_overall_status(
                mission_type,
                all_results,
                critical_base,
                critical_mission,
            ),
            base_checks=base_results,
            mission_checks=mission_results,
            critical_failures=(base_critical_failures + mission_critical_failures) or None,
            summary=self._summary(all_results),
            timestamp=time.time(),
            vehicle_id=kwargs.get("vehicle_id"),
        )