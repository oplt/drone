from __future__ import annotations

import logging

from backend.modules.property_patrol.schemas import MISSION_STATES

logger = logging.getLogger(__name__)

TERMINAL_STATES = {
    "COMPLETED", "ABORTED", "FAILED", "GEOFENCE_VIOLATION", "LOW_BATTERY_RTH",
    "LINK_LOST_RTH", "AIRSPACE_BLOCKED", "SENSOR_TRIGGER_REJECTED",
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"VALIDATED", "SENSOR_TRIGGER_REJECTED", "FAILED"},
    "VALIDATED": {"SCHEDULED", "PREFLIGHT_CHECK", "ABORTED", "FAILED"},
    "SCHEDULED": {"PREFLIGHT_CHECK", "ABORTED", "FAILED"},
    "PREFLIGHT_CHECK": {"ARMED", "ABORTED", "FAILED", "GPS_DEGRADED_HOLD", "AIRSPACE_BLOCKED"},
    "ARMED": {"TAKEOFF", "ABORTED", "RETURN_HOME", "FAILED"},
    "TAKEOFF": {"PATROL", "RETURN_HOME", "LOW_BATTERY_RTH", "LINK_LOST_RTH", "FAILED"},
    "PATROL": {"INVESTIGATE_EVENT", "PAUSED_BY_OPERATOR", "RETURN_HOME", "GEOFENCE_VIOLATION", "LOW_BATTERY_RTH", "LINK_LOST_RTH", "GPS_DEGRADED_HOLD", "FAILED"},
    "INVESTIGATE_EVENT": {"PATROL", "RETURN_HOME", "PAUSED_BY_OPERATOR", "FAILED"},
    "PAUSED_BY_OPERATOR": {"PATROL", "RETURN_HOME", "ABORTED", "FAILED"},
    "GPS_DEGRADED_HOLD": {"PATROL", "RETURN_HOME", "ABORTED", "FAILED"},
    "RETURN_HOME": {"LANDING", "ABORTED", "FAILED"},
    "LANDING": {"COMPLETED", "ABORTED", "FAILED"},
}


class PatrolMissionStateMachine:
    def transition(self, current: str, target: str, *, reason: str | None = None) -> str:
        if current not in MISSION_STATES or target not in MISSION_STATES:
            raise ValueError("Unknown Property Patrol Mission state")
        if current in TERMINAL_STATES:
            raise ValueError(f"Cannot transition from terminal state {current}")
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid Property Patrol Mission transition {current} -> {target}")
        logger.info(
            "property_patrol_state_transition",
            extra={"state_before": current, "state_after": target, "reason": reason},
        )
        return target


state_machine = PatrolMissionStateMachine()

