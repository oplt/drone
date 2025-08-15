import asyncio
import os
from drone.mavlink_drone import MavlinkDrone
from map.google_maps import GoogleMapsClient
from analysis.llm import LLMAnalyzer
from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer
from drone.orchestrator import Orchestrator
from config import settings, setup_logging
from video.stream import DroneVideoStream
from db.session import init_db, close_db
from db.repository import TelemetryRepository
from utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher



'''
        ###TO DO###
        
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
        provider=settings.llm_provider,   # NEW
    )
    mqtt = MqttClient(settings.mqtt_broker, settings.mqtt_port, settings.mqtt_user, settings.mqtt_pass,use_tls=False, client_id="drone-1")
    opcua = DroneOpcUaServer(settings.opcua_endpoint)
    
    # Initialize drone video stream with enhanced configuration
    video = None
    if settings.drone_video_enabled:
        try:
            # Parse camera source (could be int for USB camera or string for RTSP/network)
            cam_source = settings.drone_video_source
            try:
                cam_source = int(cam_source)
            except ValueError:
                pass  # Keep as string if it's not an integer
            
            video = DroneVideoStream(
                source=cam_source,
                width=settings.drone_video_width,
                height=settings.drone_video_height,
                fps=settings.drone_video_fps,
                open_timeout_s=settings.drone_video_timeout,
                probe_indices=5,  # Try /dev/video0..5 if USB camera fails
                fallback_file=settings.drone_video_fallback if settings.drone_video_fallback else None,
                fps_limit=None,  # No FPS limit for real-time drone video
                enable_recording=settings.drone_video_save_stream,
                recording_path=settings.drone_video_save_path,
                recording_format="mp4"
            )
            print(f"✅ Drone video stream initialized successfully")
            print(f"   Source: {cam_source}")
            print(f"   Resolution: {settings.drone_video_width}x{settings.drone_video_height}")
            print(f"   FPS: {settings.drone_video_fps}")
            print(f"   Recording: {'Enabled' if settings.drone_video_save_stream else 'Disabled'}")
            
        except Exception as e:
            print(f"❌ Failed to initialize drone video stream: {e}")
            print("   Continuing without video streaming...")
            video = None
    else:
        print("ℹ️  Drone video streaming disabled in configuration")
    
    repo = TelemetryRepository()
    publisher = ArduPilotTelemetryPublisher(mqtt)

    # Initialize orchestrator with video stream
    orch = Orchestrator(drone, maps, analyzer, mqtt, opcua, video, repo, publisher)

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