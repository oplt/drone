import asyncio
import os
from drone.mavlink_drone import MavlinkDrone
from map.google_maps import GoogleMapsClient
from analysis.llm import LLMAnalyzer
from telemetry.mqtt import MqttClient
from telemetry.opcua import DroneOpcUaServer
from drone.orchestrator import Orchestrator
from config import settings, setup_logging
from video.stream import DroneVideoStream
from db.session import init_db, close_db
from db.repository import TelemetryRepository
from utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher
import logging



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
    logging.info("🚀 Starting drone control system...")

    await init_db()
    logging.info("✅ Database initialized")

    # Simple optimizer - always enable
    from db.optimizer import DatabaseOptimizer
    optimizer = DatabaseOptimizer(
        check_interval=settings.DB_OPTIMIZE_INTERVAL or 3600,  # 1 hour (reduced frequency)
        optimize_threshold=1000
    )

    optimizer_task = asyncio.create_task(
        optimizer.start_monitoring(),
        name="db_optimizer"
    )


    drone = MavlinkDrone(settings.drone_conn, heartbeat_timeout=settings.heartbeat_timeout)
    maps = GoogleMapsClient(settings.google_maps_key)
    analyzer = LLMAnalyzer(
        api_base=settings.llm_api_base,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        provider=settings.llm_provider,
    )
    
    # Log LLM configuration status
    if not (settings.llm_api_base and settings.llm_model):
        logging.info("ℹ️  LLM API not configured - object detection will be disabled")
        logging.info("   Set LLM_API_BASE and LLM_MODEL environment variables to enable")
    else:
        logging.info(f"✅ LLM API configured: {settings.llm_provider} at {settings.llm_api_base}")
    mqtt = MqttClient(settings.mqtt_broker, settings.mqtt_port, settings.mqtt_user, settings.mqtt_pass,use_tls=False, client_id="drone-1")
    opcua = DroneOpcUaServer()

    # Initialize drone video stream with enhanced configuration
    # NOTE: If using Raspberry Pi camera, video stream will be initialized later
    # by raspberry_camera_task after the camera server is confirmed running
    video = None
    if settings.drone_video_enabled:
        # Only initialize video stream here if NOT using Raspberry Pi camera
        # Raspberry Pi camera stream will be initialized later in orchestrator
        if not settings.raspberry_camera_enabled:
            try:
                # For USB cameras or other direct sources
                cam_source = 0  # Default to /dev/video0
                try:
                    # Try to parse as int for USB camera index
                    cam_source = int(settings.drone_video_source) if hasattr(settings, 'drone_video_source') else 0
                except (ValueError, AttributeError):
                    # If it's a string URL, use it directly
                    cam_source = getattr(settings, 'drone_video_source', 0)

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
                logging.info(f"✅ Drone video stream initialized successfully")
                logging.info(f"   Source: {cam_source}")
                logging.info(f"   Resolution: {settings.drone_video_width}x{settings.drone_video_height}")
                logging.info(f"   FPS: {settings.drone_video_fps}")
                logging.info(f"   Recording: {'Enabled' if settings.drone_video_save_stream else 'Disabled'}")

            except Exception as e:
                logging.info(f"❌ Failed to initialize drone video stream: {e}")
                logging.info("   Continuing without video streaming...")
                video = None
        else:
            logging.info("ℹ️  Using Raspberry Pi camera - video stream will be initialized after camera server starts")
    else:
        logging.info("ℹ️  Drone video streaming disabled in configuration")

    repo = TelemetryRepository()
    # Reuse the OPC UA server started by the orchestrator; schedule updates on this event loop
    publisher = ArduPilotTelemetryPublisher(
        mqtt_client=mqtt,
        opcua_server=opcua,
        opcua_event_loop=asyncio.get_running_loop()
    )

    # Initialize orchestrator with video stream
    orch = Orchestrator(drone, maps, analyzer, mqtt, opcua, video, repo, publisher)

    # EXAMPLE: go from Antwerp Central Station to Grote Markt (Belgium examples)
    try:
        # Test flight - adjust coordinates for your location
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

