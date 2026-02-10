import asyncio
import logging

from backend.drone.mavlink_drone import MavlinkDrone
from backend.drone.orchestrator import Orchestrator
from backend.map.google_maps import GoogleMapsClient
from backend.analysis.llm import LLMAnalyzer
from backend.messaging.mqtt import MqttClient
from backend.messaging.opcua import DroneOpcUaServer
from backend.config import settings, setup_logging
from backend.video.stream import DroneVideoStream
from backend.db.session import init_db, close_db
from backend.db.repository import TelemetryRepository
from backend.utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher

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
        maps = GoogleMapsClient(settings.google_maps_key)
        analyzer = LLMAnalyzer(
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            provider=settings.llm_provider,
        )
        mqtt = MqttClient(
            settings.mqtt_broker,
            settings.mqtt_port,
            settings.mqtt_user,
            settings.mqtt_pass,
            use_tls=False,
            client_id="drone-1",
        )
        opcua = DroneOpcUaServer()

        video = None
        if settings.drone_video_enabled:
            try:
                cam_source = settings.drone_video_source
                try:
                    cam_source = int(cam_source)
                except ValueError:
                    pass

                video = DroneVideoStream(
                    source=cam_source,
                    width=settings.drone_video_width,
                    height=settings.drone_video_height,
                    fps=settings.drone_video_fps,
                    open_timeout_s=settings.drone_video_timeout,
                    probe_indices=5,
                    fallback_file=settings.drone_video_fallback if settings.drone_video_fallback else None,
                    fps_limit=None,
                    enable_recording=settings.drone_video_save_stream,
                    recording_path=settings.drone_video_save_path,
                    recording_format="mp4",
                )
                logging.info("✅ Drone video stream initialized successfully")
            except Exception as e:
                logging.info(f"❌ Failed to initialize drone video stream: {e}")
                video = None
        else:
            logging.info("ℹ️  Drone video streaming disabled in configuration")

        repo = TelemetryRepository()
        publisher = ArduPilotTelemetryPublisher(
            mqtt_client=mqtt,
            opcua_server=opcua,
            opcua_event_loop=asyncio.get_running_loop(),
        )

        _orch = Orchestrator(drone, maps, analyzer, mqtt, opcua, video, repo, publisher)
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
        logging.info("\n✅ Program terminated safely")
