from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.modules.telemetry.api import router, runtime_router
from backend.modules.telemetry.api.telemetry_route_schemas import (
    ManualControlIn,
    TelemetryConnectIn,
)
from backend.modules.telemetry.api.telemetry_route_support import (
    collect_ops_health_alerts,
    expected_drone_connect_failure,
    ops_health_overall_status,
    queue_snapshot,
    telemetry_update_age,
    velocity_for_manual_command,
)


def test_telemetry_routers_keep_public_prefixes_and_paths() -> None:
    assert router.prefix == "/telemetry"
    assert runtime_router.prefix == "/runtime"
    paths = {route.path for route in router.routes}
    assert "/telemetry/connect" in paths
    assert "/telemetry/start" in paths
    assert "/telemetry/stop" in paths
    assert "/telemetry/status" in paths
    assert "/telemetry/runtime-metrics" in paths
    assert "/telemetry/shadow-report" in paths
    assert "/telemetry/ops-health" in paths
    assert "/telemetry/manual-control" in paths
    runtime_paths = {route.path for route in runtime_router.routes}
    assert "/runtime/status" in runtime_paths


@pytest.mark.parametrize(
    "message",
    [
        "GPS home is required before arming",
        "Home fallback is disabled for this profile",
        "Heartbeat timeout waiting for vehicle",
        "Connection timed out",
        "MAVLink timeout after 5s",
    ],
)
def test_expected_drone_connect_failure_matches_known_messages(message: str) -> None:
    assert expected_drone_connect_failure(RuntimeError(message)) is True


def test_unexpected_drone_connect_failure_is_not_classified_as_expected() -> None:
    assert expected_drone_connect_failure(RuntimeError("serial port missing")) is False


def test_queue_snapshot_reports_zero_utilization_without_capacity() -> None:
    assert queue_snapshot({}, "db_event_queue") == {
        "depth": 0,
        "capacity": 0,
        "utilization_pct": 0.0,
    }


def test_queue_snapshot_rounds_utilization_percent() -> None:
    snapshot = queue_snapshot(
        {"db_event_queue_depth": 8, "db_event_queue_capacity": 10},
        "db_event_queue",
    )
    assert snapshot == {"depth": 8, "capacity": 10, "utilization_pct": 80.0}


def test_telemetry_update_age_is_none_until_first_update() -> None:
    assert telemetry_update_age(0.0, now=100.0) is None
    assert telemetry_update_age(90.0, now=100.4) == 10.4


def test_ops_health_alerts_and_status_for_stale_connected_runtime() -> None:
    alerts = collect_ops_health_alerts(
        telemetry={"running": True, "source_connected": True},
        has_recent_update=False,
        runtime_metrics={},
        labeled_queue_snapshots={
            "flight events": {"utilization_pct": 10.0},
            "mission lifecycle": {"utilization_pct": 10.0},
            "raw ingest": {"utilization_pct": 10.0},
        },
        shadow_report={"shadow_mode_active": False, "old_path": {"writes_failed": 0}},
        video_status={"available": False},
    )
    assert alerts == ["Telemetry updates are stale."]
    assert ops_health_overall_status(alerts, source_connected=True) == "degraded"


def test_ops_health_alerts_cover_queue_shadow_and_video() -> None:
    alerts = collect_ops_health_alerts(
        telemetry={"running": True, "source_connected": False},
        has_recent_update=True,
        runtime_metrics={"dropped_db_events": 3},
        labeled_queue_snapshots={
            "flight events": {"utilization_pct": 80.0},
            "mission lifecycle": {"utilization_pct": 10.0},
            "raw ingest": {"utilization_pct": 95.0},
        },
        shadow_report={"shadow_mode_active": True, "old_path": {"writes_failed": 2}},
        video_status={"available": True, "healthy": False},
    )
    assert alerts == [
        "Telemetry runtime is up, but the drone data source is disconnected.",
        "Runtime dropped DB events under queue pressure.",
        "Flight events queue utilization is above 80%.",
        "Raw ingest queue utilization is above 80%.",
        "Shadow-mode writes are failing and need investigation.",
        "Video stream health is degraded.",
    ]
    assert ops_health_overall_status(alerts, source_connected=False) == "offline"


def test_healthy_ops_status_when_no_alerts() -> None:
    assert ops_health_overall_status([], source_connected=True) == "healthy"


def test_manual_control_velocity_maps_start_and_stop_phases() -> None:
    assert velocity_for_manual_command("forward", "start") == (1.0, 0.0, 0.0, 0.0)
    assert velocity_for_manual_command("yaw_left", "hold") == (0.0, 0.0, 0.0, -30.0)
    assert velocity_for_manual_command("forward", "stop") == (0.0, 0.0, 0.0, 0.0)
    assert velocity_for_manual_command("takeoff", "start") == (0.0, 0.0, 0.0, 0.0)


def test_manual_control_schema_defaults_and_rejects_unknown_command() -> None:
    payload = ManualControlIn.model_validate({"command": "hold"})
    assert payload.phase == "start"
    assert payload.source == "keyboard"
    with pytest.raises(ValidationError):
        ManualControlIn.model_validate({"command": "strafe"})


def test_telemetry_connect_schema_accepts_empty_payload() -> None:
    payload = TelemetryConnectIn.model_validate({})
    assert payload.mission_type is None
    assert payload.flight_environment is None
