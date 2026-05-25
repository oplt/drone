from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Protocol

from backend.core.events import MissionLifecycleEnvelopeV1, TelemetryEnvelopeV1
from backend.modules.vehicle_runtime.types import Coordinate


class MapPort(Protocol):
    def geocode(self, address: str) -> Coordinate: ...

    def waypoints_between(
        self, start: Coordinate, end: Coordinate, steps: int = 5
    ) -> Iterator[Coordinate]: ...

    def elevation_m(self, lat: float, lon: float) -> float: ...


class MessagePublisherPort(Protocol):
    def publish(self, topic: str, payload: Any, qos: int = 0, retain: bool = False) -> Any: ...


class RuntimeFanoutPort(Protocol):
    async def ingest_telemetry_envelope(self, envelope: TelemetryEnvelopeV1) -> None: ...

    async def ingest_mission_lifecycle_envelope(
        self, envelope: MissionLifecycleEnvelopeV1
    ) -> None: ...

    async def broadcast(self, payload: Mapping[str, Any]) -> None: ...

    def set_runtime_active(self, *, running: bool, source_connected: bool = False) -> None: ...


class TelemetryConnectionFactoryPort(Protocol):
    def connect(self, connection_str: str) -> Any: ...

    def request_all_streams(self, connection: Any) -> None: ...


class VideoStreamPort(Protocol):
    enable_recording: bool
    source: Any

    def get_connection_status(self) -> Mapping[str, Any]: ...

    def frames(self) -> Iterator[Any]: ...

    def start_recording(self) -> Any: ...

    def close(self) -> None: ...


class VideoStreamFactoryPort(Protocol):
    def create(self) -> VideoStreamPort: ...


class SharedVideoRuntimePort(Protocol):
    async def start_recording(self) -> dict[str, Any]: ...

    async def stop_recording(self) -> dict[str, Any]: ...
