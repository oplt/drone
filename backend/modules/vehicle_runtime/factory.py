from __future__ import annotations

import asyncio
import logging
import os
import socket
from uuid import uuid4

from backend.core.config.runtime import settings
from backend.infrastructure.runtime import (
    MapAdapter,
    MavlinkVehicleAdapter,
    MqttPublisherAdapter,
    RuntimeAdapterBundle,
)
from backend.modules.telemetry.repository import TelemetryRepository
from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

_orch: Orchestrator | None = None
_orch_lock = asyncio.Lock()
_recovery_done = False


async def build_orchestrator() -> Orchestrator:
    """Create the orchestrator and all its dependencies (process-wide singleton)."""
    global _orch
    if _orch is not None:
        return _orch

    async with _orch_lock:
        if _orch is not None:
            return _orch

        drone = MavlinkVehicleAdapter(
            settings.drone_conn, heartbeat_timeout=settings.heartbeat_timeout
        )
        maps = MapAdapter(settings.google_maps_api_key)
        mqtt = None
        try:
            mqtt_client_id = (
                getattr(settings, "mqtt_client_id", None)
                or f"drone-backend-{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
            )
            logger.info(
                "Creating MQTT publisher broker=%s:%s client_id=%s pid=%s",
                settings.mqtt_broker,
                settings.mqtt_port,
                mqtt_client_id,
                os.getpid(),
            )
            mqtt = MqttPublisherAdapter(
                settings.mqtt_broker,
                settings.mqtt_port,
                settings.mqtt_user,
                settings.mqtt_pass,
                client_id=mqtt_client_id,
            )
        except Exception as exc:
            logger.warning(
                "MQTT broker unavailable (%s:%s). Continuing without MQTT. Error: %s",
                settings.mqtt_broker,
                settings.mqtt_port,
                exc,
            )

        repo = TelemetryRepository()
        adapters = RuntimeAdapterBundle()
        _orch = Orchestrator(
            drone,
            maps,
            mqtt,
            None,
            repo,
            fanout=adapters.fanout,
            telemetry_connections=adapters.telemetry_connections,
            video_factory=adapters.video_factory,
            shared_video=adapters.shared_video,
        )
        return _orch


async def get_orchestrator() -> Orchestrator:
    """Return the shared orchestrator, running mission recovery once on first access."""
    global _orch, _recovery_done
    if _orch is not None:
        return _orch
    async with _orch_lock:
        if _orch is None:
            _orch = await build_orchestrator()
            if not _recovery_done:
                from backend.modules.missions.service.recovery_service import (
                    recover_interrupted_missions,
                )

                await recover_interrupted_missions(_orch)
                _recovery_done = True
    return _orch


# Backward-compatible alias for CLI and legacy imports.
_build_orchestrator = build_orchestrator
