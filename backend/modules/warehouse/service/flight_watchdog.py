from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.modules.warehouse.service.flight_health import (
    SubsystemStatus,
    check_bridge,
    check_sensors,
)
from backend.modules.warehouse.service.flight_state_machine import (
    get_warehouse_flight_state_machine,
)
from backend.modules.warehouse.service.runtime_safety import WarehouseRuntimeSafetyTracker
from backend.modules.warehouse.service.safety import (
    WarehouseSafetyDecision,
    evaluate_warehouse_runtime_safety,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WatchdogAction:
    triggered: bool
    action: str
    reason: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class WarehouseFlightWatchdog:
    """Continuous runtime checks during autonomous warehouse flight."""

    safety_tracker: WarehouseRuntimeSafetyTracker = field(
        default_factory=WarehouseRuntimeSafetyTracker
    )
    _active: bool = field(default=False, init=False)
    _last_failure_reason: str | None = field(default=None, init=False)
    _last_log_at: float = field(default=0.0, init=False)

    def start(self) -> None:
        self._active = True
        self.safety_tracker.reset_for_takeoff()
        logger.info("Warehouse flight watchdog started")

    def stop(self) -> None:
        self._active = False
        self._last_failure_reason = None
        logger.info("Warehouse flight watchdog stopped")

    @property
    def active(self) -> bool:
        return self._active

    def evaluate(
        self,
        *,
        components: dict[str, Any],
        status: Any,
        setpoint_healthy: bool = True,
        battery_percent: float | None = None,
        min_battery_percent: float = 30.0,
    ) -> WatchdogAction:
        if not self._active:
            return WatchdogAction(False, "continue")

        bridge = check_bridge(status, components)
        if bridge.status == SubsystemStatus.FAIL:
            return self._trigger("land", "ros_bridge_lost", bridge.details)

        config = _watchdog_config()
        from backend.modules.warehouse.service.flight_health import check_slam
        from backend.modules.warehouse.service.runtime_safety import evaluate_local_odometry

        odom = evaluate_local_odometry(
            components,
            max_age_s=config.odometry_max_age_s,
            gazebo_sim=config.gazebo_sim,
            strict_topic=True,
        )
        if odom.unreadable:
            return self._trigger(
                "hover",
                "odometry_state_unreadable",
                {"display_name": odom.display_name},
            )
        if not odom.fresh:
            return self._trigger(
                "hover",
                "odometry_stale",
                {
                    "display_name": odom.display_name,
                    "odometry_age_s": odom.age_s,
                    "max_age_s": config.odometry_max_age_s,
                },
            )

        slam = check_slam(components, config)
        if slam.status == SubsystemStatus.FAIL:
            return self._trigger("hover", "localization_lost", slam.details)

        sensors = check_sensors(components, config)
        if sensors.status == SubsystemStatus.FAIL:
            if "depth" in sensors.message.lower() or "lidar" in sensors.message.lower():
                return self._trigger("hover", "depth_lidar_lost", sensors.details)
            return self._trigger("hover", "sensors_lost", sensors.details)

        if battery_percent is not None and battery_percent < min_battery_percent:
            return self._trigger(
                "return_or_land",
                "battery_low",
                {"battery_percent": battery_percent},
            )

        if not setpoint_healthy:
            return self._trigger("land", "setpoint_stream_unhealthy")

        decision = self.safety_tracker.evaluate(components, deep_health=True)
        if not decision.safe:
            return self._trigger(decision.action, decision.reason, decision.details)

        nvblox_ok = bool(components.get("nvblox_healthy", components.get("nvblox")))
        if not nvblox_ok:
            return self._trigger("hover", "nvblox_stale")

        runtime = evaluate_warehouse_runtime_safety(components)
        if not runtime.safe:
            return self._trigger(runtime.action, runtime.reason, runtime.details)

        return WatchdogAction(False, "continue")

    def _trigger(
        self,
        action: str,
        reason: str | None,
        details: dict[str, Any] | None = None,
    ) -> WatchdogAction:
        now = time.monotonic()
        if reason != self._last_failure_reason or (now - self._last_log_at) >= 5.0:
            logger.warning(
                "Warehouse flight watchdog failure action=%s reason=%s details=%s",
                action,
                reason,
                details,
            )
            self._last_failure_reason = reason
            self._last_log_at = now
            state_machine = get_warehouse_flight_state_machine()
            state_machine.enter_failure_state(action=action, reason=reason)
        return WatchdogAction(True, action, reason, details)


def _watchdog_config():
    from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig

    return WarehouseFlightConfig.from_env()


_WATCHDOG = WarehouseFlightWatchdog()


def get_warehouse_flight_watchdog() -> WarehouseFlightWatchdog:
    return _WATCHDOG


def apply_watchdog_to_safety_decision(action: WatchdogAction) -> WarehouseSafetyDecision:
    if not action.triggered:
        return WarehouseSafetyDecision(True, "continue")
    return WarehouseSafetyDecision(
        False,
        action.action,
        action.reason,
        action.details,
    )
