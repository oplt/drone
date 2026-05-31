from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


class WarehousePerceptionStatus(BaseModel):
    configured: bool
    reachable: bool
    ready: bool
    status: str
    profile: str | None = None
    bridge_url: str | None = None
    websocket_url: str | None = None
    capture_root: str | None = None
    detail: str | None = None
    components: dict[str, object] = Field(default_factory=dict)


class WarehouseMappingStartRequest(BaseModel):
    flight_id: str
    warehouse_map_id: int | None = None
    profile: str | None = None
    sensor_rig_id: int | None = None
    capture_root: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class WarehouseReplayStartRequest(BaseModel):
    replay_id: str
    rosbag_path: str
    profile: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class WarehousePerceptionCommandResult(BaseModel):
    accepted: bool
    status: str
    detail: str | None = None
    data: dict[str, object] = Field(default_factory=dict)


class WarehouseExplorationSnapshot(BaseModel):
    pose: dict[str, object] = Field(default_factory=dict)
    health: dict[str, object] = Field(default_factory=dict)
    occupancy_grid: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class WarehousePerceptionPort(Protocol):
    async def status(self, *, deep: bool = False) -> WarehousePerceptionStatus: ...

    async def exploration_snapshot(self) -> WarehouseExplorationSnapshot: ...

    async def start_mapping(
        self, request: WarehouseMappingStartRequest
    ) -> WarehousePerceptionCommandResult: ...

    async def stop_mapping(self, *, flight_id: str) -> WarehousePerceptionCommandResult: ...

    async def download_artifacts(self, *, flight_id: str, destination_dir: Path) -> list[str]: ...

    async def start_replay(
        self, request: WarehouseReplayStartRequest
    ) -> WarehousePerceptionCommandResult: ...

    async def stop_replay(self, *, replay_id: str) -> WarehousePerceptionCommandResult: ...
