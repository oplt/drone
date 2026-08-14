from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.modules.agriculture.contracts import MissionTelemetrySample
from backend.modules.agriculture.georeferencing import NearestTelemetryMatcher
from backend.modules.agriculture.ports import telemetry as telemetry_port
from backend.scripts.check_module_ports import collect_violations


@pytest.mark.asyncio
async def test_telemetry_port_returns_ordered_persistence_neutral_dtos(monkeypatch):
    captured = datetime(2026, 8, 12, 10, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            id=42,
            timestamp_utc=captured,
            lat=50,
            lon=4,
            relative_altitude_m=12,
            absolute_altitude_m=100,
            roll_deg=1,
            pitch_deg=2,
            yaw_deg=3,
            gps_quality=0.9,
        )
    ]

    async def list_telemetry(_db, *, flight_id):
        assert flight_id == "mission-1"
        return rows

    monkeypatch.setattr(
        telemetry_port.agriculture_repository, "list_telemetry", list_telemetry
    )
    result = await telemetry_port.list_mission_telemetry_for_georef(
        SimpleNamespace(), mission_id="mission-1"
    )

    assert result == [
        MissionTelemetrySample(
            timestamp_utc=captured,
            lat=50.0,
            lon=4.0,
            relative_altitude_m=12,
            absolute_altitude_m=100,
            roll_deg=1,
            pitch_deg=2,
            yaw_deg=3,
            gps_quality=0.9,
            id=42,
        )
    ]
    match = NearestTelemetryMatcher("mission-1", result, captured).match(0)
    assert (match.lat, match.lon, match.altitude_m, match.heading_deg) == (
        50.0,
        4.0,
        12,
        3,
    )
    assert match.sample_ids == (42,)
    assert match.method == "nearest"


def test_module_port_dependency_guard_has_no_violations():
    assert collect_violations() == []


def test_module_port_dependency_guard_detects_reverse_repository_import(tmp_path):
    source = tmp_path / "backend/modules/video_analysis/bad.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from backend.modules.agriculture.repository import agriculture_repository\n",
        encoding="utf-8",
    )

    violations = collect_violations(tmp_path / "backend/modules")

    assert len(violations) == 1
    assert violations[0].imported == "backend.modules.agriculture.repository"


def test_module_port_dependency_guard_detects_vision_video_repository_import(tmp_path):
    source = tmp_path / "backend/modules/vision_models/bad.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from backend.modules.video_analysis.repository import VideoAnalysisRepository\n",
        encoding="utf-8",
    )

    violations = collect_violations(tmp_path / "backend/modules")

    assert len(violations) == 1
    assert violations[0].imported == "backend.modules.video_analysis.repository"


def test_module_port_dependency_guard_detects_vision_video_models_import(tmp_path):
    source = tmp_path / "backend/modules/vision_models/bad.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from backend.modules.video_analysis.models import VideoAsset\n",
        encoding="utf-8",
    )

    violations = collect_violations(tmp_path / "backend/modules")

    assert len(violations) == 1
    assert violations[0].imported == "backend.modules.video_analysis.models"


def test_module_port_dependency_guard_detects_vision_video_service_import(tmp_path):
    source = tmp_path / "backend/modules/vision_models/bad.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from backend.modules.video_analysis.service.geo import NearestTelemetryMatcher\n",
        encoding="utf-8",
    )

    violations = collect_violations(tmp_path / "backend/modules")

    assert len(violations) == 1
    assert violations[0].imported == "backend.modules.video_analysis.service.geo"


def test_module_port_dependency_guard_detects_agriculture_video_repository_import(
    tmp_path,
):
    source = tmp_path / "backend/modules/agriculture/bad.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from backend.modules.video_analysis.repository import VideoAnalysisRepository\n",
        encoding="utf-8",
    )

    violations = collect_violations(tmp_path / "backend/modules")

    assert len(violations) == 1
    assert violations[0].imported == "backend.modules.video_analysis.repository"


def test_module_port_dependency_guard_allows_video_analysis_contracts(tmp_path):
    source = tmp_path / "backend/modules/vision_models/ok.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from backend.modules.video_analysis.contracts import video_analysis_port\n",
        encoding="utf-8",
    )

    assert collect_violations(tmp_path / "backend/modules") == []


def test_module_port_dependency_guard_flags_blocking_vehicle_import_in_api(tmp_path):
    source = tmp_path / "backend/modules/missions/api/routes.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from backend.infrastructure.vehicle.mavlink_client import MavlinkDrone\n",
        encoding="utf-8",
    )

    violations = collect_violations(tmp_path / "backend/modules")

    assert len(violations) == 1
    assert "run_blocking" in violations[0].reason


def test_module_port_dependency_guard_allows_blocking_vehicle_with_run_blocking(tmp_path):
    source = tmp_path / "backend/modules/missions/api/routes.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from backend.infrastructure.runtime.blocking import run_blocking\n"
        "from backend.infrastructure.vehicle.mavlink_client import MavlinkDrone\n",
        encoding="utf-8",
    )

    assert collect_violations(tmp_path / "backend/modules") == []
