import time
import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
from .preflight_context import PreflightContext
from .schemas import PreflightReport, CheckResult, CheckStatus
from .base import BasePreflightChecks
from .mission_specific import create_mission_preflight
from .cache import TerrainCache
from .models import PrecomputedMissionData, MissionDataPreprocessor
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


    async def _build_context(
            self,
            vehicle_state: Any,
            mission: Mission,
            **kwargs
    ) -> PreflightContext:
        """Build context with concurrent terrain prefetch."""
        precomputed = None
        if mission.waypoints:
            preprocessor = MissionDataPreprocessor(terrain_cache=self.terrain_cache)
            precomputed = await preprocessor.preprocess(
                mission.waypoints,
                terrain_data=kwargs.get('terrain_provider')
            )

        return PreflightContext(
            vehicle_state=vehicle_state,
            mission=mission,
            precomputed=precomputed,
            terrain_cache=self.terrain_cache,
            **{k: kwargs.get(k) for k in [
                'terrain_provider', 'wind_data', 'no_fly_zones',
                'obstacle_map', 'geofence_polygon', 'config_overrides',
                'vehicle_id', 'flight_id'
            ]}
        )


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


    async def run(
            self,
            vehicle_state: Any,
            mission_data: Union[Dict, Mission],
            **kwargs
    ) -> PreflightReport:
        """Async preflight run — base and mission checks run concurrently."""
        # Validate mission
        if isinstance(mission_data, dict):
            mission = create_mission_from_dict(mission_data)
        else:
            mission = mission_data

        # Build context (fetches terrain concurrently)
        context = await self._build_context(vehicle_state, mission, **kwargs)

        # Calculate estimated time
        total_distance = context.total_distance()
        speed = getattr(mission, 'speed', None) or 10
        estimated_time_s = kwargs.get('estimated_time_s') or (total_distance / speed)

        # Run base checks
        base_checker = BasePreflightChecks(context)
        base_results = await base_checker.run(
            estimated_time_s=estimated_time_s,
            mission_waypoints=mission.waypoints,
            expected_mission_count=len(mission.waypoints),
            mission_crc=kwargs.get('mission_crc'),
        )

        # Early exit on critical base failures
        has_critical_fail, failed_critical = self._check_for_critical_fails(
            base_results, "base"
        )

        mission_results = []
        if not (has_critical_fail and self.early_terminate_on_fail):
            mission_checker = create_mission_preflight(context)
            mission_results = await mission_checker.run()

            has_cm_fail, failed_cm = self._check_for_critical_fails(
                mission_results, "mission"
            )
            has_critical_fail = has_critical_fail or has_cm_fail
            failed_critical.extend(failed_cm)

        all_results = base_results + mission_results
        overall = self._determine_overall_status(all_results)
        summary = self._generate_summary(all_results)
        summary['cache_stats'] = context.cache_stats

        return PreflightReport(
            mission_type=getattr(mission, 'type', 'unknown'),
            overall_status=overall,
            base_checks=base_results,
            mission_checks=mission_results,
            summary=summary,
            timestamp=context.timestamp,
            vehicle_id=context.vehicle_id,
            critical_failures=failed_critical or None,
            mission_checks_skipped=(has_critical_fail and self.early_terminate_on_fail)
        )
