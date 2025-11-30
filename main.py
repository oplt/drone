import asyncio
import os
from drone.mavlink_drone import MavlinkDrone
from map.google_maps import GoogleMapsClient
from analysis.llm import LLMAnalyzer
from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer
from drone.orchestrator import Orchestrator
from config import settings, setup_logging, VideoAnalysisConfig
from db.session import init_db, close_db
from db.repository import TelemetryRepository
from utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher
import logging
import cv2
from video.stream import RaspberryClient

'''        ###TO DO###        
- remove mqtt publishing functions and replace mqtt listening functions
- telemetry raw data recording is ok. Add a group of message in a row !!! Necessary??
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
    setup_logging()

    await init_db()

    drone = MavlinkDrone(settings.drone_conn, heartbeat_timeout=settings.heartbeat_timeout)
    maps = GoogleMapsClient(settings.google_maps_key)
    analyzer = LLMAnalyzer(
        api_base=settings.llm_api_base,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        provider=settings.llm_provider,
    )
    mqtt = MqttClient(settings.mqtt_broker, settings.mqtt_port, settings.mqtt_user, settings.mqtt_pass,use_tls=False, client_id="drone-1")
    opcua = DroneOpcUaServer()
    repo = TelemetryRepository()
    publisher = ArduPilotTelemetryPublisher(
        mqtt_client=mqtt,
        opcua_server=opcua,
        opcua_event_loop=asyncio.get_running_loop()
    )
    video_cfg = VideoAnalysisConfig()
    video = None

    if settings.drone_video_enabled:
        try:
            video = RaspberryClient()
            logging.info(f"✅ Drone video stream initialized successfully")
        except Exception as e:
            logging.info(f"❌ Failed to initialize drone video stream: {e}")
            logging.info("   Continuing without video streaming...")
            video = None
    else:
        logging.info("ℹ️  Drone video streaming disabled in configuration")

    orch = Orchestrator(drone, maps, analyzer, mqtt, opcua, video, repo, publisher, video_cfg=video_cfg,)

    try:
        await orch.run("Jerrabomberra Grassland Nature Reserve", "Alexander Maconochie Centre", alt=35)
    except KeyboardInterrupt:
        logging.info("\n🛑 Manual abort - triggering safe shutdown")
        orch._running = False
    except Exception as e:
        logging.info(f"❌ Flight failed: {e}")
    finally:
        await close_db()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\n✅ Program terminated safely")


    '''
        # kill opc ua server ports
        sudo lsof -i :4840
        sudo kill -9 <PID>
    '''

