from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from pymavlink import mavutil

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime import shared_video_runtime
from backend.infrastructure.camera.stream_client import DroneVideoStream
from backend.infrastructure.maps.google_maps_client import GoogleMapsClient
from backend.infrastructure.messaging.mqtt_client import MqttClient
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.infrastructure.vehicle.mavlink_client import MavlinkDrone


class MavlinkVehicleAdapter(MavlinkDrone):
    """Vehicle-control adapter exposed to the runtime composition root."""


class MapAdapter(GoogleMapsClient):
    """Map/elevation adapter exposed through the runtime map port."""


class MqttPublisherAdapter(MqttClient):
    """MQTT publisher adapter exposed through the runtime publishing port."""


class MavlinkTelemetryConnectionFactory:
    def connect(self, connection_str: str) -> Any:
        return mavutil.mavlink_connection(
            connection_str,
            autoreconnect=True,
            retries=3,
            source_system=255,
        )

    def request_all_streams(self, connection: Any) -> None:
        connection.mav.request_data_stream_send(
            connection.target_system,
            connection.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            10,
            1,
        )


class VideoStreamFactory:
    def create(self) -> DroneVideoStream:
        source: Any = settings.drone_video_source
        with suppress(ValueError, TypeError):
            source = int(source)
        return DroneVideoStream(
            source=source,
            width=settings.drone_video_width,
            height=settings.drone_video_height,
            fps=settings.drone_video_fps,
            open_timeout_s=settings.drone_video_timeout,
            probe_indices=5,
            fallback_file=settings.drone_video_fallback or None,
            fps_limit=None,
            enable_recording=settings.drone_video_save_stream,
            recording_path=settings.drone_video_save_path,
            recording_format="mp4",
        )


@dataclass(frozen=True)
class RuntimeAdapterBundle:
    fanout: Any = telemetry_manager
    telemetry_connections: Any = field(default_factory=MavlinkTelemetryConnectionFactory)
    video_factory: Any = field(default_factory=VideoStreamFactory)
    shared_video: Any = shared_video_runtime
