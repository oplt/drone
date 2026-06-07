from backend.modules.missions.flight_profile import (
    FlightEnvironment,
    flight_profile_for_environment,
    flight_profile_for_mission_type,
)
from backend.modules.missions.schemas.mission_types import MissionType


def test_outdoor_missions_use_global_profile() -> None:
    profile = flight_profile_for_mission_type(MissionType.GRID)

    assert profile.environment == FlightEnvironment.OUTDOOR_GLOBAL
    assert profile.requires_gps_home is True
    assert profile.allows_indoor_home_fallback is False


def test_warehouse_missions_use_indoor_local_profile() -> None:
    profile = flight_profile_for_mission_type(MissionType.WAREHOUSE_SCAN)

    assert profile.environment == FlightEnvironment.INDOOR_LOCAL
    assert profile.requires_gps_home is False
    assert profile.allows_indoor_home_fallback is True


def test_environment_override_supports_indoor_controlled_flight() -> None:
    profile = flight_profile_for_environment("indoor_local")

    assert profile.environment == FlightEnvironment.INDOOR_LOCAL
    assert profile.control_mode == "local_setpoint"

