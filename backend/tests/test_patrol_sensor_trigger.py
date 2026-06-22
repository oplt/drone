from __future__ import annotations

from backend.modules.patrol.geo import (
    distance_point_to_polygon_m,
    point_in_geofence_within_m,
    point_in_polygon,
)
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


def test_sensor_trigger_geofence_tolerance_accepts_nearby_point() -> None:
    square = (
        (5.340248304054398, 50.92896501756738),
        (5.342778061908689, 50.92896501756738),
        (5.342778061908689, 50.92802937584108),
        (5.340248304054398, 50.92802937584108),
    )
    lon, lat = 5.340658744235307, 50.92926892125356
    assert not validate_location_in_geofence(lon, lat, square)
    assert point_in_geofence_within_m(lat, lon, square, tolerance_m=75.0)
    assert distance_point_to_polygon_m(lat, lon, square) < 40.0


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


def test_preflight_block_detail_lists_failed_checks() -> None:
    from backend.modules.preflight.checks.schemas import CheckResult, CheckStatus
    from backend.modules.patrol.trigger_dispatch import _preflight_block_http_detail

    class _Report:
        overall_status = "FAIL"
        summary = {"failed": 2}
        base_checks = [
            CheckResult(
                name="Geofence",
                status=CheckStatus.FAIL,
                message="Current position outside geofence",
            )
        ]
        mission_checks = [
            CheckResult(
                name="Geofence Containment",
                status=CheckStatus.FAIL,
                message="Point 2 outside geofence",
            )
        ]

    detail = _preflight_block_http_detail(_Report())
    assert "Geofence" in detail["message"]
    assert len(detail["failed_checks"]) == 2
