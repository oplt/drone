from __future__ import annotations

from backend.modules.patrol.geo import point_in_polygon
from backend.modules.patrol.sensor_config_schemas import PatrolSensorTriggerIn
from backend.modules.patrol.trigger_dispatch import (
    choose_response_mode,
    resolve_trigger_location,
    validate_location_in_geofence,
)


def test_resolve_trigger_location_prefers_coordinates() -> None:
    resolved = resolve_trigger_location(
        trigger_coordinates=(-122.1, 37.4),
        sensor_id="gate-1",
        sensor_registry={"gate-1": (-122.0, 37.0)},
    )
    assert resolved == (-122.1, 37.4)


def test_resolve_trigger_location_uses_sensor_registry() -> None:
    resolved = resolve_trigger_location(
        trigger_coordinates=None,
        sensor_id="gate-1",
        sensor_registry={"gate-1": (-122.0, 37.0)},
    )
    assert resolved == (-122.0, 37.0)


def test_choose_response_mode() -> None:
    assert choose_response_mode((1.0, 2.0)) == "incident_response"
    assert choose_response_mode(None) == "detection_search"


def test_geofence_validation() -> None:
    square = ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0))
    assert validate_location_in_geofence(0.5, 0.5, square)
    assert not validate_location_in_geofence(2.0, 2.0, square)
    assert point_in_polygon(0.5, 0.5, square)


def test_sensor_trigger_payload_allows_optional_sensor_id() -> None:
    payload = PatrolSensorTriggerIn(trigger_id="evt-1")
    assert payload.sensor_id is None
    assert payload.field_id is None


def test_create_mission_from_dict_requires_type_not_task_type() -> None:
    from backend.modules.missions.schemas.mission_types import create_mission_from_dict
    import pytest

    with pytest.raises(ValueError, match="Unknown mission type"):
        create_mission_from_dict(
            {"task_type": "event_triggered_patrol", "response_mode": "incident_response"}
        )
