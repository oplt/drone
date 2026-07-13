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
from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.telemetry.repository import TelemetryRepository
from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

_orch: Orchestrator | None = None
_orch_lock = asyncio.Lock()
_recovery_done = False

_MQTT_PROBE_TIMEOUT_S = 1.0


def _mqtt_broker_reachable(host: str, port: int, *, timeout_s: float = _MQTT_PROBE_TIMEOUT_S) -> bool:
    """Fast TCP probe so orchestrator init does not block on dead MQTT brokers."""
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _create_mqtt_publisher() -> MqttPublisherAdapter:
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
    return MqttPublisherAdapter(
        settings.mqtt_broker,
        settings.mqtt_port,
        settings.mqtt_user,
        settings.mqtt_pass,
        client_id=mqtt_client_id,
        connect_timeout=2,
        max_retries=1,
    )


async def _build_orchestrator_unlocked() -> Orchestrator:
    """Construct a new orchestrator. Caller must already hold ``_orch_lock``."""
    drone = MavlinkVehicleAdapter(
        settings.drone_conn, heartbeat_timeout=settings.heartbeat_timeout
    )
    maps = MapAdapter(settings.google_maps_api_key)
    mqtt = None
    broker = settings.mqtt_broker
    port = settings.mqtt_port
    if _mqtt_broker_reachable(broker, port):
        try:
            mqtt = await asyncio.to_thread(_create_mqtt_publisher)
        except Exception as exc:
            logger.warning(
                "MQTT broker unavailable (%s:%s). Continuing without MQTT. Error: %s",
                broker,
                port,
                exc,
            )
    else:
        logger.warning(
            "MQTT broker unreachable (%s:%s). Skipping MQTT publisher.",
            broker,
            port,
        )

    repo = TelemetryRepository()
    adapters = RuntimeAdapterBundle()
    return Orchestrator(
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


async def reset_orchestrator() -> None:
    """Drop the cached orchestrator so the next access rebuilds with fresh settings."""
    global _orch
    async with _orch_lock:
        if _orch is None:
            return
        drone = getattr(_orch, "drone", None)
        if drone is not None:
            try:
                await run_blocking(
                    drone.close,
                    boundary="mavlink",
                    operation="vehicle_close",
                    timeout_s=30.0,
                )
            except Exception:
                logger.exception("Failed closing MAVLink vehicle during orchestrator reset")
        _orch = None


async def build_orchestrator() -> Orchestrator:
    """Create the orchestrator and all its dependencies (process-wide singleton)."""
    global _orch
    if _orch is not None:
        return _orch

    async with _orch_lock:
        if _orch is not None:
            return _orch
        _orch = await _build_orchestrator_unlocked()
        return _orch


async def get_orchestrator() -> Orchestrator:
    """Return the shared orchestrator, running mission recovery once on first access."""
    global _orch, _recovery_done
    if _orch is not None:
        return _orch
    async with _orch_lock:
        if _orch is None:
            _orch = await _build_orchestrator_unlocked()
            if not _recovery_done:
                from backend.modules.missions.service.recovery_service import (
                    recover_interrupted_missions,
                )

                await recover_interrupted_missions(_orch)
                _recovery_done = True
    return _orch


# Backward-compatible alias for CLI and legacy imports.
_build_orchestrator = build_orchestrator
