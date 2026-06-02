from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum

from backend.modules.warehouse.service.flight_health import SubsystemStatus
from backend.modules.warehouse.service.flight_readiness import WarehouseFlightReadiness

logger = logging.getLogger(__name__)


class WarehouseFlightState(StrEnum):
    IDLE = "IDLE"
    SYSTEM_CHECK = "SYSTEM_CHECK"
    SENSOR_CHECK = "SENSOR_CHECK"
    LOCALIZATION_CHECK = "LOCALIZATION_CHECK"
    MAPPING_CHECK = "MAPPING_CHECK"
    ARM_READY = "ARM_READY"
    TAKEOFF = "TAKEOFF"
    MISSION_READY = "MISSION_READY"
    AUTONOMOUS_FLIGHT = "AUTONOMOUS_FLIGHT"
    PAUSE = "PAUSE"
    HOVER = "HOVER"
    LAND = "LAND"
    FAILSAFE = "FAILSAFE"
    ERROR = "ERROR"


_CRITICAL_FAILURE_STATES = frozenset(
    {
        WarehouseFlightState.PAUSE,
        WarehouseFlightState.HOVER,
        WarehouseFlightState.LAND,
        WarehouseFlightState.FAILSAFE,
        WarehouseFlightState.ERROR,
    }
)


@dataclass
class WarehouseFlightStateMachine:
    state: WarehouseFlightState = WarehouseFlightState.IDLE
    _last_transition_at: float = field(default_factory=time.monotonic, init=False)
    _last_logged_state: WarehouseFlightState | None = field(default=None, init=False)
    _last_log_at: float = field(default=0.0, init=False)

    def reset(self) -> None:
        self.transition(WarehouseFlightState.IDLE, reason="reset")

    def transition(
        self,
        new_state: WarehouseFlightState,
        *,
        reason: str | None = None,
    ) -> bool:
        if new_state == self.state:
            return False
        old = self.state
        self.state = new_state
        self._last_transition_at = time.monotonic()
        now = time.monotonic()
        if self._last_logged_state != new_state or (now - self._last_log_at) >= 10.0:
            logger.info(
                "Warehouse flight state transition %s -> %s reason=%s",
                old.value,
                new_state.value,
                reason,
            )
            self._last_logged_state = new_state
            self._last_log_at = now
        return True

    def sync_from_readiness(
        self,
        readiness: WarehouseFlightReadiness,
        *,
        in_flight: bool = False,
        user_armed: bool = False,
        autonomous: bool = False,
    ) -> WarehouseFlightState:
        if in_flight and autonomous:
            self.transition(WarehouseFlightState.AUTONOMOUS_FLIGHT, reason="autonomous_active")
            return self.state
        if in_flight and user_armed:
            self.transition(WarehouseFlightState.TAKEOFF, reason="takeoff_active")
            return self.state

        sub = readiness.subsystems
        bridge_ok = sub["bridge"].status == SubsystemStatus.OK
        autopilot_ok = sub["autopilot"].status in {SubsystemStatus.OK, SubsystemStatus.WARN}
        sensors_ok = sub["sensors"].status == SubsystemStatus.OK
        slam_ok = sub["slam"].status == SubsystemStatus.OK
        nvblox_ok = sub["nvblox"].status == SubsystemStatus.OK
        planner_ok = sub["planner"].status == SubsystemStatus.OK

        if readiness.ready_for_autonomy:
            target = WarehouseFlightState.MISSION_READY
        elif readiness.ready_to_takeoff:
            target = WarehouseFlightState.ARM_READY if not user_armed else WarehouseFlightState.TAKEOFF
        elif slam_ok and sensors_ok:
            target = WarehouseFlightState.MAPPING_CHECK if not nvblox_ok else WarehouseFlightState.ARM_READY
        elif sensors_ok:
            target = WarehouseFlightState.LOCALIZATION_CHECK
        elif bridge_ok and autopilot_ok:
            target = WarehouseFlightState.SENSOR_CHECK
        elif bridge_ok:
            target = WarehouseFlightState.SYSTEM_CHECK
        else:
            target = WarehouseFlightState.SYSTEM_CHECK

        if not bridge_ok or not autopilot_ok:
            target = WarehouseFlightState.SYSTEM_CHECK
        elif not sensors_ok:
            target = WarehouseFlightState.SENSOR_CHECK
        elif not slam_ok:
            target = WarehouseFlightState.LOCALIZATION_CHECK
        elif not nvblox_ok:
            target = WarehouseFlightState.MAPPING_CHECK
        elif readiness.ready_for_autonomy and planner_ok:
            target = WarehouseFlightState.MISSION_READY
        elif readiness.ready_to_takeoff:
            target = WarehouseFlightState.ARM_READY

        if self.state not in _CRITICAL_FAILURE_STATES:
            self.transition(target, reason="readiness_sync")
        return self.state

    def enter_failure_state(
        self,
        *,
        action: str,
        reason: str | None = None,
    ) -> WarehouseFlightState:
        mapping = {
            "hover": WarehouseFlightState.HOVER,
            "pause": WarehouseFlightState.PAUSE,
            "land": WarehouseFlightState.LAND,
            "return_or_land": WarehouseFlightState.FAILSAFE,
            "return_or_relocalize": WarehouseFlightState.FAILSAFE,
        }
        target = mapping.get(action, WarehouseFlightState.ERROR)
        self.transition(target, reason=reason or action)
        return self.state


_FLIGHT_STATE_MACHINE = WarehouseFlightStateMachine()


def get_warehouse_flight_state_machine() -> WarehouseFlightStateMachine:
    return _FLIGHT_STATE_MACHINE
