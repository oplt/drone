from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.modules.patrol.planning import generate_private_patrol_plan
from backend.modules.property_patrol.models import PropertyPatrolSite, PropertyPatrolTemplate
from backend.modules.property_patrol.schemas import SensorEventCreate
from backend.modules.property_patrol.services.policy import policy_engine
from backend.modules.property_patrol.services.preflight import preflight_validator
from backend.modules.property_patrol.services.route_planner import route_planner
from backend.modules.property_patrol.services.sensor_events import sensor_event_validator
from backend.modules.property_patrol.services.state_machine import state_machine


SAFE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [5.1200, 50.1200],
            [5.1240, 50.1200],
            [5.1240, 50.1230],
            [5.1200, 50.1230],
            [5.1200, 50.1200],
        ]
    ],
}

NO_FLY = {
    "type": "Polygon",
    "coordinates": [
        [
            [5.1210, 50.1210],
            [5.1220, 50.1210],
            [5.1220, 50.1220],
            [5.1210, 50.1220],
            [5.1210, 50.1210],
        ]
    ],
}


def _site(*, no_fly: list[dict] | None = None) -> PropertyPatrolSite:
    return PropertyPatrolSite(
        id=1,
        name="Test Site",
        property_boundary=SAFE_POLYGON,
        flight_safe_area=SAFE_POLYGON,
        no_fly_zones=no_fly or [],
        privacy_zones=[],
        emergency_landing_zones=[],
        default_altitude_m=30,
    )


def _template(mode: str = "perimeter") -> PropertyPatrolTemplate:
    return PropertyPatrolTemplate(
        id=2,
        site_id=1,
        name="Template",
        patrol_mode=mode,
        altitude_m=30,
        speed_mps=6,
        boundary_offset_m=5,
        grid_spacing_m=40,
        overlap_percent=50,
        camera_direction="inward",
        camera_gimbal_pitch_deg=35,
        max_mission_duration_minutes=25,
        min_battery_return_percent=30,
        trigger_behavior="approval_required",
        ai_detection_enabled=True,
        llm_summary_enabled=False,
        privacy_blur_faces=True,
        privacy_blur_license_plates=True,
        event_clip_recording_only=True,
        retention_hours_or_days="72h",
    )


def test_perimeter_route_stays_inside_safe_polygon() -> None:
    site = _site()
    template = _template("perimeter")

    waypoints, _stats = route_planner.generate(site=site, template=template)
    result = policy_engine.validate_route(site=site, template=template, waypoints=waypoints)

    assert waypoints
    assert result.ok is True


def test_private_patrol_reduces_offset_for_small_property() -> None:
    small_property = [
        (5.1200, 50.1200),
        (5.1203, 50.1200),
        (5.1203, 50.1202),
        (5.1200, 50.1202),
    ]

    plan = generate_private_patrol_plan(
        small_property,
        altitude_agl_m=30,
        path_offset_m=15,
        direction="clockwise",
        max_segment_length_m=20,
    )

    assert plan.waypoints
    assert 0 < plan.stats["path_offset_applied_m"] < 15


def test_grid_route_stays_inside_safe_polygon() -> None:
    site = _site()
    template = _template("grid")

    waypoints, _stats = route_planner.generate(site=site, template=template)
    result = policy_engine.validate_route(site=site, template=template, waypoints=waypoints)

    assert waypoints
    assert result.ok is True


def test_policy_rejects_waypoint_outside_safe_area() -> None:
    result = policy_engine.validate_route(
        site=_site(),
        template=_template(),
        waypoints=[{"lat": 51.0, "lon": 6.0, "alt": 30}],
    )

    assert result.ok is False
    assert any(error.code == "outside_safe_area" for error in result.errors)


def test_policy_rejects_waypoint_inside_no_fly_zone() -> None:
    result = policy_engine.validate_route(
        site=_site(no_fly=[NO_FLY]),
        template=_template(),
        waypoints=[{"lat": 50.1215, "lon": 5.1215, "alt": 30}],
    )

    assert result.ok is False
    assert any(error.code == "inside_no_fly_zone" for error in result.errors)


def test_policy_rejects_unsafe_altitude_and_sensor_outside_site() -> None:
    route = policy_engine.validate_route(
        site=_site(),
        template=_template(),
        waypoints=[{"lat": 50.1205, "lon": 5.1205, "alt": 500}],
    )
    sensor = policy_engine.validate_sensor_location(
        site=_site(),
        approx_location={"lat": 51.0, "lon": 6.0},
    )

    assert any(error.code == "unsafe_altitude" for error in route.errors)
    assert any(error.code == "sensor_outside_safe_area" for error in sensor.errors)


def test_state_machine_allows_valid_and_blocks_invalid_transitions() -> None:
    assert state_machine.transition("DRAFT", "VALIDATED") == "VALIDATED"

    with pytest.raises(ValueError):
        state_machine.transition("DRAFT", "TAKEOFF")

    with pytest.raises(ValueError):
        state_machine.transition("COMPLETED", "PATROL")


def test_preflight_blocks_empty_route_and_low_battery() -> None:
    result = asyncio.run(preflight_validator.validate(
        route_waypoints=[],
        telemetry={"battery_remaining": 10, "gps_ok": True, "connected": True},
    ))

    assert result.ok is False
    assert {error.code for error in result.errors} >= {"route_not_loaded", "battery_low"}


class _NoDuplicateDb:
    async def scalar(self, _stmt):
        return None


def test_sensor_event_validator_accepts_valid_event() -> None:
    payload = SensorEventCreate(
        sensor_id="gate_camera_01",
        external_event_id="evt_valid",
        event_type="possible_intrusion",
        confidence=0.84,
        site_id=1,
        zone_id="north_gate",
        timestamp=datetime.now(UTC),
        approx_location={"lat": 50.1205, "lon": 5.1205},
    )

    result = asyncio.run(sensor_event_validator.validate(
        db=_NoDuplicateDb(),  # type: ignore[arg-type]
        site=_site(),
        payload=payload,
    ))

    assert result.ok is True


def test_sensor_event_validator_rejects_old_and_low_confidence_event() -> None:
    payload = SensorEventCreate(
        sensor_id="gate_camera_01",
        external_event_id="evt_old",
        event_type="possible_intrusion",
        confidence=0.2,
        site_id=1,
        timestamp=datetime.now(UTC) - timedelta(hours=1),
        approx_location={"lat": 50.1205, "lon": 5.1205},
    )

    result = asyncio.run(sensor_event_validator.validate(
        db=_NoDuplicateDb(),  # type: ignore[arg-type]
        site=_site(),
        payload=payload,
    ))

    assert result.ok is False
    assert {error.code for error in result.errors} >= {"event_too_old", "low_confidence"}
