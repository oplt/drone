from __future__ import annotations

from typing import Any, List, Optional

from .base import BasePreflightChecks, CheckSpec, Priority
from .schemas import CheckResult, CheckStatus


class IndoorWarehouseBasePreflightChecks(BasePreflightChecks):
    """Indoor preflight profile for local-frame warehouse exploration."""

    def _required_bool_check(
        self,
        *,
        name: str,
        value: Any,
        ok_message: str,
        fail_message: str,
        missing_message: str,
    ) -> List[CheckResult]:
        if value is True:
            return [self._ok(name, ok_message)]
        if value is False:
            return [self._fail(name, fail_message)]
        return [self._fail(name, missing_message)]

    async def check_estimator_ready(self) -> List[CheckResult]:
        estimator_ready = self._value("estimator_ready")
        if estimator_ready is None:
            estimator_ready = self._value("ekf_ok")
        return self._required_bool_check(
            name="Indoor Estimator",
            value=estimator_ready,
            ok_message="Estimator is ready for local indoor flight",
            fail_message="Estimator is not ready for indoor flight",
            missing_message="Estimator readiness is unavailable",
        )

    async def check_local_position_source(self) -> List[CheckResult]:
        local_ok = self._value("local_position_ok")
        if local_ok is True:
            return [self._ok("Indoor Local Position", "Local position stream is healthy")]
        north = self._value("local_north_m")
        east = self._value("local_east_m")
        down = self._value("local_down_m")
        if north is not None and east is not None and down is not None:
            return [self._ok("Indoor Local Position", "Local position vector is populated")]
        return [self._fail("Indoor Local Position", "Indoor mission requires a live local position source")]

    async def check_lidar_stream(self) -> List[CheckResult]:
        return self._required_bool_check(
            name="Indoor LiDAR",
            value=self._value("lidar_healthy"),
            ok_message="LiDAR stream is healthy",
            fail_message="LiDAR stream is unhealthy",
            missing_message="LiDAR health is unavailable",
        )

    async def check_rangefinder_health(self) -> List[CheckResult]:
        value = self._value("rangefinder_healthy")
        if value is None:
            ceiling_distance = self._value("ceiling_distance_m")
            if ceiling_distance is not None:
                return [self._ok("Indoor Rangefinder", f"Altitude source available ({float(ceiling_distance):.2f}m)")]
        return self._required_bool_check(
            name="Indoor Rangefinder",
            value=value,
            ok_message="Rangefinder / indoor altitude source is healthy",
            fail_message="Rangefinder / indoor altitude source is unhealthy",
            missing_message="Rangefinder / indoor altitude source is unavailable",
        )

    async def check_proximity_health(self) -> List[CheckResult]:
        required = bool(self.ctx.get_threshold("INDOOR_PROXIMITY_REQUIRED", True))
        value = self._value("proximity_healthy")
        if value is None and not required:
            return [self._skip("Indoor Proximity", "Indoor proximity source is not required")]
        if value is None:
            return [self._fail("Indoor Proximity", "Indoor proximity source is unavailable")]
        if value is True:
            return [self._ok("Indoor Proximity", "Indoor proximity source is healthy")]
        return [self._fail("Indoor Proximity", "Indoor proximity source is unhealthy")]

    async def check_slam_pipeline(self) -> List[CheckResult]:
        slam_ready = self._value("slam_ready")
        slam_tracking_ok = self._value("slam_tracking_ok")
        localization_confidence = self._value("localization_confidence")
        confidence_min = float(self.ctx.get_threshold("INDOOR_PREFLIGHT_LOCALIZATION_MIN", 0.55))

        if slam_ready is False or slam_tracking_ok is False:
            return [self._fail("Indoor SLAM Pipeline", "SLAM / localization pipeline is not healthy")]
        if localization_confidence is not None and float(localization_confidence) < confidence_min:
            return [
                self._fail(
                    "Indoor SLAM Pipeline",
                    f"Localization confidence {float(localization_confidence):.2f} < {confidence_min:.2f}",
                )
            ]
        if slam_ready is True or slam_tracking_ok is True:
            return [self._ok("Indoor SLAM Pipeline", "SLAM / localization pipeline is ready")]
        if self._value("local_position_ok") is True and self._value("lidar_healthy") is True:
            return [self._ok("Indoor SLAM Pipeline", "Local position and LiDAR imply indoor localization is available")]
        return [self._fail("Indoor SLAM Pipeline", "SLAM / localization readiness is unavailable")]

    async def check_dock_reference(self) -> List[CheckResult]:
        dock_reference_ready = self._value("dock_reference_ready")
        if dock_reference_ready is False:
            return [self._fail("Indoor Dock Reference", "Dock reference could not be initialized")]

        dock = getattr(self.ctx.mission, "dock", None)
        if dock is None:
            return [self._fail("Indoor Dock Reference", "Mission is missing dock reference data")]

        if dock_reference_ready is True:
            return [self._ok("Indoor Dock Reference", "Dock reference is initialized")]
        return [self._ok("Indoor Dock Reference", "Dock reference provided in mission configuration")]

    async def check_takeoff_bubble(self) -> List[CheckResult]:
        required_clearance = float(
            getattr(self.ctx.mission, "safe_takeoff_bubble_radius_m", 1.5)
        )
        clearance = self._value("takeoff_clearance_m", "obstacle_distance_m")
        if clearance is None:
            return [self._fail("Indoor Takeoff Bubble", "Takeoff bubble clearance is unavailable")]
        if float(clearance) < required_clearance:
            return [
                self._fail(
                    "Indoor Takeoff Bubble",
                    f"Measured clearance {float(clearance):.2f}m < required {required_clearance:.2f}m",
                )
            ]
        return [self._ok("Indoor Takeoff Bubble", f"Clearance {float(clearance):.2f}m")]

    def _specs(
        self,
        *,
        estimated_time_s: Optional[float],
        mission_ah_req: Optional[float],
        allowed_modes: Optional[List[str]],
        gps_timeout_s: float,
        mission_waypoints: Optional[List[Any]],
        expected_mission_count: Optional[int],
        mission_crc: Optional[int],
    ) -> List[CheckSpec]:
        del gps_timeout_s, mission_waypoints, expected_mission_count, mission_crc
        return [
            CheckSpec("Link Health", Priority.CRITICAL, True, lambda: self.check_link_health()),
            CheckSpec("Arming Checks", Priority.CRITICAL, True, lambda: self.check_arming_checks()),
            CheckSpec("Vehicle Readiness", Priority.CRITICAL, True, lambda: self.check_vehicle_readiness(allowed_modes=allowed_modes)),
            CheckSpec("Indoor Estimator", Priority.CRITICAL, True, lambda: self.check_estimator_ready()),
            CheckSpec("Indoor Local Position", Priority.CRITICAL, True, lambda: self.check_local_position_source()),
            CheckSpec("Battery", Priority.CRITICAL, True, lambda: self.check_battery(estimated_time_s=estimated_time_s, mission_ah_req=mission_ah_req)),
            CheckSpec("Indoor LiDAR", Priority.CRITICAL, True, lambda: self.check_lidar_stream()),
            CheckSpec("Indoor Rangefinder", Priority.CRITICAL, True, lambda: self.check_rangefinder_health()),
            CheckSpec("Indoor SLAM Pipeline", Priority.CRITICAL, True, lambda: self.check_slam_pipeline()),
            CheckSpec("Indoor Dock Reference", Priority.CRITICAL, True, lambda: self.check_dock_reference()),
            CheckSpec("Indoor Takeoff Bubble", Priority.CRITICAL, True, lambda: self.check_takeoff_bubble()),
            CheckSpec("Indoor Proximity", Priority.SAFETY, True, lambda: self.check_proximity_health()),
            CheckSpec("IMU", Priority.QUALITY, False, lambda: self.check_imu_calibration()),
            CheckSpec("Storage/Logging", Priority.QUALITY, False, lambda: self.check_storage_logging()),
        ]
