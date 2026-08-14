from __future__ import annotations

from backend.infrastructure.messaging.websocket_publisher import telemetry_manager


def drone_video_link_connected() -> bool:
    return bool(telemetry_manager.runtime_snapshot().get("source_connected"))

