import asyncio
from config import settings
from core.mavlink_drone import MavlinkDrone
from core.google_maps import GoogleMapsClient
from core.llm import LLMAnalyzer
from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer
from core.orchestrator import Orchestrator
from config import settings
import os
from core.stream import VideoStream
from db.repository import TelemetryRepository
from db.session import init_db, close_db

cam_source = settings.cam_source

try:
    cam_source = int(cam_source)
except ValueError:
    pass



async def main():
    await init_db()

    drone = MavlinkDrone(settings.drone_conn)
    maps = GoogleMapsClient(settings.google_maps_key)
    analyzer = LLMAnalyzer(
        api_base=settings.llm_api_base,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        provider=settings.llm_provider,   # NEW
    )
    mqtt = MqttClient(settings.mqtt_broker, settings.mqtt_port, settings.mqtt_user, settings.mqtt_pass,use_tls=False)
    opcua = DroneOpcUaServer(settings.opcua_endpoint)
    video = VideoStream(
        source=cam_source,                 # e.g., 0 or "rtsp://<ip>/stream"
        width=640,
        height=480,
        open_timeout_s=5.0,
        probe_indices=5,                   # try /dev/video0..5 if 0 fails
        fallback_file=os.getenv("CAM_FALLBACK", ""),  # e.g., "/home/polat/sample.mp4"
        fps_limit=1.0
    )
    repo = TelemetryRepository()

    orch = Orchestrator(drone, maps, analyzer, mqtt, opcua, video)

    # EXAMPLE: go from Antwerp Central Station to Grote Markt (Belgium examples)
    try:
        await orch.run("Antwerp Central Station", "Grote Markt, Antwerp", alt=35)
    finally:
        await close_db()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
