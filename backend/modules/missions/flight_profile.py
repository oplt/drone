from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.core.config.runtime import env_truthy, settings
from backend.modules.missions.schemas.mission_types import MissionType


class FlightEnvironment(str, Enum):
    OUTDOOR_GLOBAL = "outdoor_global"
    INDOOR_LOCAL = "indoor_local"


@dataclass(frozen=True)
class FlightProfile:
    environment: FlightEnvironment
    control_mode: str
    requires_gps_home: bool
    allows_indoor_home_fallback: bool

    @property
    def allows_home_fallback(self) -> bool:
        return self.allows_indoor_home_fallback or explicit_sim_home_fallback_enabled()


INDOOR_MISSION_TYPES = {
    MissionType.WAREHOUSE_SCAN.value,
    MissionType.WAREHOUSE_INSPECTION.value,
    MissionType.INDOOR_EXPLORATION.value,
}


OUTDOOR_GLOBAL_PROFILE = FlightProfile(
    environment=FlightEnvironment.OUTDOOR_GLOBAL,
    control_mode="global_waypoint",
    requires_gps_home=True,
    allows_indoor_home_fallback=False,
)

INDOOR_LOCAL_PROFILE = FlightProfile(
    environment=FlightEnvironment.INDOOR_LOCAL,
    control_mode="local_setpoint",
    requires_gps_home=False,
    allows_indoor_home_fallback=True,
)


def mission_type_value(mission_type: Any) -> str:
    if isinstance(mission_type, MissionType):
        return mission_type.value
    value = getattr(mission_type, "value", mission_type)
    return str(value or "").strip().lower()


def explicit_sim_home_fallback_enabled() -> bool:
    warehouse_bridge_flow = settings.WAREHOUSE_BRIDGE_FLOW.strip().lower()
    if warehouse_bridge_flow == "gazebo":
        return True
    if env_truthy(settings.sim_mode) or env_truthy(settings.indoor_nav):
        return True
    if env_truthy(settings.warehouse_gazebo_sim):
        return True
    return False


def flight_profile_for_mission_type(mission_type: Any) -> FlightProfile:
    if mission_type_value(mission_type) in INDOOR_MISSION_TYPES:
        return INDOOR_LOCAL_PROFILE
    return OUTDOOR_GLOBAL_PROFILE


def flight_profile_for_environment(environment: Any) -> FlightProfile:
    value = str(getattr(environment, "value", environment) or "").strip().lower()
    if value == FlightEnvironment.INDOOR_LOCAL.value:
        return INDOOR_LOCAL_PROFILE
    return OUTDOOR_GLOBAL_PROFILE
