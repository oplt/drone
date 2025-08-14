import asyncio
from drone.mavlink_drone import MavlinkDrone
from map.google_maps import GoogleMapsClient
from analysis.llm import LLMAnalyzer
from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer
from drone.orchestrator import Orchestrator
from config import settings
import os
from video.stream import VideoStream
from db.session import init_db, close_db
from db.repository import TelemetryRepository
from utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher
import logging

logging.basicConfig(
                    level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[
                        logging.FileHandler("drone.log"),
                        logging.StreamHandler()  # still print to console
                    ]
                )

cam_source = settings.cam_source

try:
    cam_source = int(cam_source)
except ValueError:
    pass


'''
        ###TO DO###
        
- remove mqtt publishing functions and replace mqtt listening functions
- telemtery database is not recording
- test video streaming and saving to db
- check flow
- check calculations
- find a proper LLM for trash detection, agriculture and defense
- mosquito listener:
mosquitto_sub -h 127.0.0.1 -p 1883 -t "ardupilot/telemetry" -v


RASPBERRY PI SETUP:
- CHECK IF THE DRONE IS CONNECTED TO THE BROKER AND IF NOT, RECONNECT
- CHECK HEARTBEATS ON THE BROKER AND ADD self.drone.set_mode("RTL") IN CASE OF NO HEARTBEAT

 
'''

async def main():
    await init_db()

    drone = MavlinkDrone(settings.drone_conn, heartbeat_timeout=settings.heartbeat_timeout)
    maps = GoogleMapsClient(settings.google_maps_key)
    analyzer = LLMAnalyzer(
        api_base=settings.llm_api_base,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        provider=settings.llm_provider,   # NEW
    )
    mqtt = MqttClient(settings.mqtt_broker, settings.mqtt_port, settings.mqtt_user, settings.mqtt_pass,use_tls=False, client_id="drone-1")
    opcua = DroneOpcUaServer(settings.opcua_endpoint)
    # video = VideoStream(
    #     source=cam_source,                 # e.g., 0 or "rtsp://<ip>/stream"
    #     width=640,
    #     height=480,
    #     open_timeout_s=5.0,
    #     probe_indices=5,                   # try /dev/video0..5 if 0 fails
    #     fallback_file=os.getenv("CAM_FALLBACK", ""),  # e.g., "/home/polat/sample.mp4"
    #     fps_limit=1.0
    # )
    repo = TelemetryRepository()
    publisher = ArduPilotTelemetryPublisher(mqtt)

    # orch = Orchestrator(drone, maps, analyzer, mqtt, opcua, video)
    orch = Orchestrator(drone, maps, analyzer, mqtt, opcua, repo, publisher)

    # EXAMPLE: go from Antwerp Central Station to Grote Markt (Belgium examples)
    try:
        # Test flight - adjust coordinates for your location

        await orch.run("Jerrabomberra Grassland Nature Reserve", "Alexander Maconochie Centre", alt=35)
    except KeyboardInterrupt:
        logging.info("\n🛑 Manual abort - triggering safe shutdown")
        # print("\n🛑 Manual abort - triggering safe shutdown")
        orch._running = False
    except Exception as e:
        logging.info(f"❌ Flight failed: {e}")
        # print(f"❌ Flight failed: {e}")
    finally:
        await close_db()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\n✅ Program terminated safely")
        # print("\n✅ Program terminated safely")