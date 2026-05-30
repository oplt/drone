from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.modules.warehouse.planning import scan as scan_module
from backend.modules.warehouse.planning.scan import WarehouseScanMission
from backend.modules.warehouse.ports import (
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
    WarehouseReplayStartRequest,
)


class _Repo:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, dict[str, object]]] = []

    async def add_event(self, flight_id: int, event_type: str, data: dict[str, object]) -> None:
        self.events.append((flight_id, event_type, data))


class _FakePerceptionPort:
    def __init__(self, artifact: Path) -> None:
        self.artifact = artifact
        self.start_request: WarehouseMappingStartRequest | None = None
        self.stopped_flight_id: str | None = None

    async def status(self) -> object:
        return SimpleNamespace(ready=True)

    async def start_mapping(
        self, request: WarehouseMappingStartRequest
    ) -> WarehousePerceptionCommandResult:
        self.start_request = request
        return WarehousePerceptionCommandResult(
            accepted=True,
            status="running",
            data={"session_dir": "/data/warehouse/flight_42"},
        )

    async def stop_mapping(self, *, flight_id: str) -> WarehousePerceptionCommandResult:
        self.stopped_flight_id = flight_id
        return WarehousePerceptionCommandResult(accepted=True, status="stopped")

    async def download_artifacts(self, *, flight_id: str, destination_dir: Path) -> list[str]:
        del flight_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        dst = destination_dir / self.artifact.name
        dst.write_text(self.artifact.read_text(encoding="utf-8"), encoding="utf-8")
        return [str(dst)]

    async def start_replay(
        self, request: WarehouseReplayStartRequest
    ) -> WarehousePerceptionCommandResult:
        del request
        return WarehousePerceptionCommandResult(accepted=True, status="running")

    async def stop_replay(self, *, replay_id: str) -> WarehousePerceptionCommandResult:
        del replay_id
        return WarehousePerceptionCommandResult(accepted=True, status="stopped")


def test_warehouse_scan_uses_perception_port_for_capture_lifecycle(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    artifact = tmp_path / "mesh.ply"
    artifact.write_text("ply", encoding="utf-8")
    port = _FakePerceptionPort(artifact)
    monkeypatch.setattr(scan_module, "build_warehouse_perception_port", lambda: port)
    repo = _Repo()
    orch = SimpleNamespace(_flight_id=42, repo=repo)
    mission = WarehouseScanMission(
        area_polygon_local_m=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
        warehouse_map_id=7,
        warehouse_name="Aisle A",
        sensor_rig_id=3,
        reference_mapping_job_id=5,
    )
    destination = tmp_path / "capture"

    start = asyncio.run(mission._start_perception_mapping(orch, session_dir=destination))
    paths = asyncio.run(mission._download_perception_artifacts(orch, destination_dir=destination))
    stop = asyncio.run(mission._stop_perception_mapping(orch))

    assert start.accepted is True
    assert stop.status == "stopped"
    assert port.start_request is not None
    assert port.start_request.flight_id == "42"
    assert port.start_request.warehouse_map_id == 7
    assert port.start_request.sensor_rig_id == 3
    assert port.start_request.metadata["warehouse_name"] == "Aisle A"
    assert port.stopped_flight_id == "42"
    assert paths == [str(destination / "mesh.ply")]
    event_types = [event_type for _flight_id, event_type, _data in repo.events]
    assert "warehouse_scan_perception_mapping_started" in event_types
    assert "warehouse_scan_perception_artifacts_downloaded" in event_types
    assert "warehouse_scan_perception_mapping_stopped" in event_types
