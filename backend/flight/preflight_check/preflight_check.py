import time
import logging
from typing import Dict, Any, List, Optional, Union
from .preflight_context import PreflightContext
from .schemas import PreflightReport, CheckResult, CheckStatus
from .base import BasePreflightChecks
from .mission_specific import (
    GridMissionPreflight,
    TerrainFollowMissionPreflight,
    OrbitMissionPreflight,
    PerimeterPatrolMissionPreflight,
    AdaptiveAltitudeMissionPreflight,
    create_mission_preflight
)
from .cache import TerrainCache, DistanceCache
from .models import MissionDataPreprocessor, PrecomputedMissionData
from ..missions.schemas import create_mission_from_dict, Mission

logger = logging.getLogger(__name__)


# Define critical checks that should cause early termination
CRITICAL_BASE_CHECKS = [
    "MAVLink Link",
    "GPS Lock",
    "Heartbeat Age",  # From enhanced checks
    "GPS Fix Type",    # From enhanced checks
    "Vehicle Armable", # Can't proceed if vehicle isn't armable
    "EKF Health",      # Navigation solution is critical
]

CRITICAL_MISSION_CHECKS = [
    "Grid Camera Footprint",  # Mission feasibility
    "Orbit Bank Angle",       # Safety-critical
    "Orbit Lateral Acceleration",  # Safety-critical
    "Cornering Limits",       # Mission feasibility
]


class PreflightOrchestrator:
    """Orchestrates all preflight checks."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the orchestrator.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Initialize caches
        self.terrain_cache = TerrainCache(
            precision=self.config.get('terrain_cache_precision', 1e-5),
            ttl_seconds=self.config.get('terrain_cache_ttl', 300)
        )
        self.preprocessor = MissionDataPreprocessor(terrain_cache=self.terrain_cache)

        # Critical checks
        self.critical_base_checks = self.config.get(
            'critical_base_checks',
            CRITICAL_BASE_CHECKS
        )
        self.critical_mission_checks = self.config.get(
            'critical_mission_checks',
            CRITICAL_MISSION_CHECKS
        )
        self.early_terminate_on_fail = self.config.get(
            'early_terminate_on_fail',
            True
        )

    def _build_context(
            self,
            vehicle_state: Any,
            mission: Mission,
            **kwargs
    ) -> PreflightContext:

        precomputed = None
        if mission.waypoints:
            precomputed = PrecomputedMissionData(
                waypoints=mission.waypoints
            )
            # Precompute terrain if provider available
            if kwargs.get('terrain_provider'):
                for wp in mission.waypoints:
                    elev = kwargs['terrain_provider'].get_elevation(wp.lat, wp.lon)
                    precomputed.terrain_elevations.append(elev if elev is not None else None)
            else:
                precomputed.terrain_elevations = [None] * len(mission.waypoints)

        # Build context
        context = PreflightContext(
            vehicle_state=vehicle_state,
            mission=mission,
            timestamp=kwargs.get('timestamp', time.time()),
            terrain_provider=kwargs.get('terrain_provider'),
            wind_data=kwargs.get('wind_data'),
            no_fly_zones=kwargs.get('no_fly_zones'),
            obstacle_map=kwargs.get('obstacle_map'),
            geofence_polygon=kwargs.get('geofence_polygon'),
            precomputed=precomputed,
            terrain_cache=self.terrain_cache,
            config_overrides=kwargs.get('config_overrides', {}),
            vehicle_id=kwargs.get('vehicle_id'),
            flight_id=kwargs.get('flight_id')
        )

        return context

    def _check_for_critical_fails(
            self,
            results: List[CheckResult],
            check_type: str = "base"
    ) -> tuple[bool, List[CheckResult]]:
        """Check if any critical checks have failed."""
        critical_list = (self.critical_base_checks if check_type == "base"
                         else self.critical_mission_checks)

        failed_critical = []
        for result in results:
            if result.name in critical_list and result.status == CheckStatus.FAIL:
                failed_critical.append(result)

        return len(failed_critical) > 0, failed_critical

    def run(
            self,
            vehicle_state: Any,
            mission_data: Union[Dict, Mission],
            **kwargs
    ) -> PreflightReport:
        """
        Run all preflight checks.

        Args:
            vehicle_state: Vehicle telemetry snapshot
            mission_data: Either a mission dict or validated Mission object
            **kwargs: Additional data:
                - terrain_provider: Object with get_elevation method
                - wind_data: Dict with speed, gust, direction
                - no_fly_zones: List of no-fly zones
                - obstacle_map: Obstacle map data
                - geofence_polygon: List of waypoints defining geofence
                - config_overrides: Dict of threshold overrides
                - timestamp: Current timestamp
                - vehicle_id: Vehicle identifier
                - flight_id: Flight identifier

        Returns:
            PreflightReport with all check results
        """
        # Validate mission
        if isinstance(mission_data, dict):
            try:
                mission = create_mission_from_dict(mission_data)
                logger.info(f"✅ Validated mission: {mission.type}")
            except Exception as e:
                logger.error(f"❌ Mission validation failed: {e}")
                raise ValueError(f"Invalid mission data: {e}")
        else:
            mission = mission_data

        # Build context
        context = self._build_context(vehicle_state, mission, **kwargs)

        # Log cache stats before running
        logger.debug(f"Terrain cache stats: {context.cache_stats}")

        # Calculate estimated time
        estimated_time_s = kwargs.get('estimated_time_s')
        if estimated_time_s is None:
            total_distance = context.total_distance()
            speed = mission.speed if hasattr(mission, 'speed') and mission.speed else 10
            estimated_time_s = total_distance / speed if speed > 0 else 0

        # Run base checks
        base_checker = BasePreflightChecks(context)
        base_results = base_checker.run(
            estimated_time_s=estimated_time_s,
            mission_waypoints=mission.waypoints if hasattr(mission, 'waypoints') else None,
            expected_mission_count=len(mission.waypoints) if hasattr(mission, 'waypoints') else None,
            mission_crc=kwargs.get('mission_crc'),
            mission_ah_req=kwargs.get('mission_ah_req'),
            allowed_modes=kwargs.get('allowed_modes')
        )

        # Check for critical failures
        has_critical_fail, failed_critical = self._check_for_critical_fails(base_results, "base")

        mission_results = []

        # Run mission checks if no critical failures
        if not (has_critical_fail and self.early_terminate_on_fail):
            mission_checker = create_mission_preflight(context)
            mission_results = mission_checker.run()

            # Check for critical mission failures
            has_critical_mission_fail, failed_mission_critical = self._check_for_critical_fails(
                mission_results, "mission"
            )
            has_critical_fail = has_critical_fail or has_critical_mission_fail
            failed_critical.extend(failed_mission_critical)
        else:
            logger.warning(
                f"Skipping mission checks due to critical base failures: "
                f"{[c.name for c in failed_critical]}"
            )

        # Combine results
        all_results = base_results + mission_results

        # Determine overall status
        overall = self._determine_overall_status(all_results)

        # Generate summary
        summary = self._generate_summary(all_results)

        # Add cache stats to summary
        summary['cache_stats'] = context.cache_stats

        return PreflightReport(
            mission_type=mission.type if hasattr(mission, 'type') else "unknown",
            overall_status=overall,
            base_checks=base_results,
            mission_checks=mission_results,
            summary=summary,
            timestamp=context.timestamp,
            vehicle_id=context.vehicle_id,
            critical_failures=failed_critical if failed_critical else None,
            mission_checks_skipped=(has_critical_fail and self.early_terminate_on_fail)
        )

    def _determine_overall_status(self, results: List[CheckResult]) -> CheckStatus:
        """Determine overall status from results."""
        has_fail = any(r.status == CheckStatus.FAIL for r in results)
        has_warn = any(r.status == CheckStatus.WARN for r in results)

        if has_fail:
            return CheckStatus.FAIL
        elif has_warn:
            return CheckStatus.WARN
        else:
            return CheckStatus.PASS

    def _generate_summary(self, results: List[CheckResult]) -> Dict[str, Any]:
        """Generate summary statistics."""
        summary = {
            'total_checks': len(results),
            'passed': sum(1 for r in results if r.status == CheckStatus.PASS),
            'failed': sum(1 for r in results if r.status == CheckStatus.FAIL),
            'warned': sum(1 for r in results if r.status == CheckStatus.WARN),
            'skipped': sum(1 for r in results if r.status == CheckStatus.SKIP),
        }
        return summary

    def run_quick_check(self, vehicle_state: Any, mission: Mission, **kwargs) -> PreflightReport:
        """
        Run a quick subset of checks for preliminary assessment.

        Args:
            vehicle_state: Vehicle telemetry snapshot
            mission: Mission object
            **kwargs: Additional data

        Returns:
            PreflightReport with only critical checks
        """
        # Build context
        context = self._build_context(vehicle_state, mission, **kwargs)

        # Calculate estimated time
        estimated_time_s = kwargs.get('estimated_time_s')
        if estimated_time_s is None:
            total_distance = context.total_distance()
            speed = mission.speed if hasattr(mission, 'speed') and mission.speed else 10
            estimated_time_s = total_distance / speed if speed > 0 else 0

        # Critical checks only
        base_checker = BasePreflightChecks(context)
        all_base = base_checker.run(
            estimated_time_s=estimated_time_s,
            mission_waypoints=mission.waypoints if hasattr(mission, 'waypoints') else None,
            expected_mission_count=len(mission.waypoints) if hasattr(mission, 'waypoints') else None,
            mission_crc=kwargs.get('mission_crc'),
            mission_ah_req=kwargs.get('mission_ah_req'),
            allowed_modes=kwargs.get('allowed_modes')
        )

        # Filter to critical checks
        base_results = [r for r in all_base if r.name in self.critical_base_checks]

        # Check for critical failures
        has_critical_fail, failed_critical = self._check_for_critical_fails(base_results, "base")

        mission_results = []
        if not (has_critical_fail and self.early_terminate_on_fail):
            # Run critical mission checks only
            mission_checker = create_mission_preflight(context)
            all_mission = mission_checker.run()
            # Filter to critical mission checks
            mission_results = [r for r in all_mission
                               if r.name in self.critical_mission_checks]

        all_results = base_results + mission_results
        overall = self._determine_overall_status(all_results)

        return PreflightReport(
            mission_type=mission.type if hasattr(mission, 'type') else "unknown",
            overall_status=overall,
            base_checks=base_results,
            mission_checks=mission_results,
            summary=self._generate_summary(all_results),
            timestamp=context.timestamp,
            vehicle_id=context.vehicle_id,
            quick_check=True,
            critical_failures=failed_critical if failed_critical else None,
            mission_checks_skipped=(has_critical_fail and self.early_terminate_on_fail)
        )


# Convenience function for simple use cases
def run_preflight_checks(vehicle_state: Any, mission: Union[Dict, Mission], **kwargs) -> PreflightReport:
    """
    Convenience function to run preflight checks.

    Args:
        vehicle_state: Vehicle state object
        mission: Mission object or dictionary
        **kwargs: Additional parameters for checks

    Returns:
        PreflightReport object
    """
    orchestrator = PreflightOrchestrator(kwargs.get('config', {}))
    return orchestrator.run(vehicle_state, mission, **kwargs)