import asyncio
import logging

from backend.analysis.llm import LLMAnalyzer

# from backend.messaging.opcua import DroneOpcUaServer
from backend.config import settings, setup_logging
from backend.db.repository.telemetry_repo import TelemetryRepository
from backend.db.session import close_db, init_db
from backend.drone.mavlink_drone import MavlinkDrone
from backend.drone.orchestrator import Orchestrator
from backend.map.google_maps import GoogleMapsClient
from backend.messaging.mqtt import MqttClient

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

        drone = MavlinkDrone(settings.drone_conn, heartbeat_timeout=settings.heartbeat_timeout)
        maps = GoogleMapsClient(settings.google_maps_api_key)
        analyzer = LLMAnalyzer(
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            provider=settings.llm_provider,
        )
        mqtt = None
        try:
            mqtt = MqttClient(
                settings.mqtt_broker,
                settings.mqtt_port,
                settings.mqtt_user,
                settings.mqtt_pass,
                # use_tls=settings.mqtt_use_tls,
                # ca_certs=settings.mqtt_ca_certs or None,
                client_id="drone-1",
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

        _orch = Orchestrator(drone, maps, analyzer, mqtt, video, repo)
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
