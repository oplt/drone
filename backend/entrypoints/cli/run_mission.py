import asyncio
import logging
import os
import socket
from uuid import uuid4

# from backend.infrastructure.messaging.opcua_server import DroneOpcUaServer
from backend.core.config.runtime import settings, setup_logging
from backend.core.database.session import close_db, init_db
from backend.infrastructure.ai.llm_client import LLMAnalyzer
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


async def _build_orchestrator() -> Orchestrator:
    """Create the orchestrator and all its dependencies (single instance)."""
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
        analyzer = LLMAnalyzer(
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            provider=settings.llm_provider,
        )
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
                # use_tls=settings.mqtt_use_tls,
                # ca_certs=settings.mqtt_ca_certs or None,
                client_id=mqtt_client_id,
            )

        except Exception as e:
            logger.warning(
                "MQTT broker unavailable (%s:%s). Continuing without MQTT. Error: %s",
                settings.mqtt_broker,
                settings.mqtt_port,
                e,
            )
        # opcua = DroneOpcUaServer()

        # Video stream is initialized lazily when a flight starts (drone must be connected first).
        video = None

        repo = TelemetryRepository()

        adapters = RuntimeAdapterBundle()
        _orch = Orchestrator(
            drone,
            maps,
            analyzer,
            mqtt,
            video,
            repo,
            fanout=adapters.fanout,
            telemetry_connections=adapters.telemetry_connections,
            video_factory=adapters.video_factory,
            shared_video=adapters.shared_video,
        )
        return _orch


# Optional CLI entrypoint
async def main():
    setup_logging()
    await init_db()
    orch = await _build_orchestrator()
    await orch.run("Jerrabomberra Grassland Nature Reserve", "Alexander Maconochie Centre", alt=35)
    await close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program terminated safely")
