from __future__ import annotations

from typing import Any

from .base import BasePreflightChecks, CheckSpec, Priority
from .schemas import CheckResult


class WarehouseRosBasePreflightChecks(BasePreflightChecks):
    """ROS/Gazebo warehouse preflight — no MAVLink telemetry gates."""

    async def check_warehouse_local_position(self) -> list[CheckResult]:
        local_ok = self._value("local_position_ok")
        if local_ok is True:
            return [self._ok("Warehouse ROS Position", "Local odometry position is available")]
        north = self._value("local_north_m")
        east = self._value("local_east_m")
        down = self._value("local_down_m")
        if north is not None and east is not None and down is not None:
            return [self._ok("Warehouse ROS Position", "Local position vector is populated")]
        return [
            self._fail(
                "Warehouse ROS Position",
                "Warehouse mission requires live local odometry from the ROS bridge",
            )
        ]

    async def check_warehouse_odometry(self) -> list[CheckResult]:
        healthy = self._value("odometry_healthy")
        drift = self._value("odometry_drift_m")
        max_drift = float(self.ctx.get_threshold("WAREHOUSE_ODOMETRY_DRIFT_MAX_M", 0.75))
        if healthy is False:
            return [
                self._fail(
                    "Warehouse ROS Odometry",
                    "Visual SLAM / local odometry is unhealthy",
                )
            ]
        if drift is not None and float(drift) > max_drift:
            return [
                self._fail(
                    "Warehouse ROS Odometry",
                    f"Odometry drift {float(drift):.2f}m exceeds {max_drift:.2f}m",
                )
            ]
        if healthy is True or drift is not None:
            detail = (
                f"Odometry drift {float(drift):.2f}m"
                if drift is not None
                else "Odometry healthy"
            )
            return [self._ok("Warehouse ROS Odometry", detail)]
        return [
            self._fail(
                "Warehouse ROS Odometry",
                "Odometry health is missing from warehouse ROS state",
            )
        ]

    def _specs(
        self,
        *,
        estimated_time_s: float | None,
        mission_ah_req: float | None,
        allowed_modes: list[str] | None,
        gps_timeout_s: float,
        mission_waypoints: list[Any] | None,
        expected_mission_count: int | None,
        mission_crc: int | None,
    ) -> list[CheckSpec]:
        del (
            estimated_time_s,
            mission_ah_req,
            allowed_modes,
            gps_timeout_s,
            mission_waypoints,
            expected_mission_count,
            mission_crc,
        )
        return [
            CheckSpec(
                "Warehouse ROS Position",
                Priority.CRITICAL,
                True,
                lambda: self.check_warehouse_local_position(),
            ),
            CheckSpec(
                "Warehouse ROS Odometry",
                Priority.CRITICAL,
                True,
                lambda: self.check_warehouse_odometry(),
            ),
        ]
