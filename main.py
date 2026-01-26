import asyncio
import os
import argparse
from drone.mavlink_drone import MavlinkDrone
from map.google_maps import GoogleMapsClient
from analysis.llm import LLMAnalyzer
from telemetry.mqtt import MqttClient
from drone.orchestrator import Orchestrator
from config import settings, setup_logging
from video.stream import DroneVideoStream
from db.session import init_db, close_db
from db.repository import TelemetryRepository
from telemetry.publisher import TelemetryPublisher
import logging

"""
        ###TO DO###
        
- add mqtt publishing functions on raspbi for gps wifi connection
- send heartbeat from pc to raspi, if no heartbeat then return to home location
- telemetry messages are not seen on dashboard graphs
- when anomaly is detected by llm save images and add show detections on dashboard
- show video stream on dashboard
- cursor on map is not moving during flight
- get config variables from db
- check calculations

"""


async def main(
    start_lat=None,
    start_lon=None,
    start_alt=35.0,
    dest_lat=None,
    dest_lon=None,
    dest_alt=35.0,
    user_id=None,
):
    setup_logging()
    logging.info("🚀 Starting drone control system...")

    # Set user_id in environment if provided (for flight tracking)
    if user_id is not None:
        os.environ["FLIGHT_USER_ID"] = str(user_id)

    await init_db()
    logging.info("✅ Database initialized")

    # Simple optimizer - always enable
    from db.optimizer import DatabaseOptimizer

    optimizer = DatabaseOptimizer(
        check_interval=settings.DB_OPTIMIZE_INTERVAL
        or 3600,  # 1 hour (reduced frequency)
        optimize_threshold=1000,
    )

    asyncio.create_task(optimizer.start_monitoring(), name="db_optimizer")

    # Log connection string for debugging
    logging.info(f"Drone connection string: {settings.drone_conn}")
    logging.info(f"Heartbeat timeout: {settings.heartbeat_timeout}s")
    logging.info(f"Baud rate: {settings.drone_baud_rate}")

    drone = MavlinkDrone(
        settings.drone_conn,
        heartbeat_timeout=settings.heartbeat_timeout,
        baud_rate=settings.drone_baud_rate,
    )
    logging.info("✅ MavlinkDrone instance created")
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
        logging.info(
            "   Set LLM_API_BASE and LLM_MODEL environment variables to enable"
        )
    else:
        logging.info(
            f"✅ LLM API configured: {settings.llm_provider} at {settings.llm_api_base}"
        )
    mqtt = MqttClient(
        settings.mqtt_broker,
        settings.mqtt_port,
        settings.mqtt_user,
        settings.mqtt_pass,
        use_tls=False,
        client_id="drone-1",
    )

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
                    cam_source = (
                        int(settings.drone_video_source)
                        if hasattr(settings, "drone_video_source")
                        else 0
                    )
                except (ValueError, AttributeError):
                    # If it's a string URL, use it directly
                    cam_source = getattr(settings, "drone_video_source", 0)

                video = DroneVideoStream(
                    source=cam_source,
                    width=settings.drone_video_width,
                    height=settings.drone_video_height,
                    fps=settings.drone_video_fps,
                    open_timeout_s=settings.drone_video_timeout,
                    probe_indices=5,  # Try /dev/video0..5 if USB camera fails
                    fallback_file=(
                        settings.drone_video_fallback
                        if settings.drone_video_fallback
                        else None
                    ),
                    fps_limit=None,  # No FPS limit for real-time drone video
                    enable_recording=settings.drone_video_save_stream,
                    recording_path=settings.drone_video_save_path,
                    recording_format="mp4",
                )
                logging.info("✅ Drone video stream initialized successfully")
                logging.info(f"   Source: {cam_source}")
                logging.info(
                    f"   Resolution: {settings.drone_video_width}x{settings.drone_video_height}"
                )
                logging.info(f"   FPS: {settings.drone_video_fps}")
                logging.info(
                    f"   Recording: {'Enabled' if settings.drone_video_save_stream else 'Disabled'}"
                )

            except Exception as e:
                logging.info(f"❌ Failed to initialize drone video stream: {e}")
                logging.info("   Continuing without video streaming...")
                video = None
        else:
            logging.info(
                "ℹ️  Using Raspberry Pi camera - video stream will be initialized after camera server starts"
            )
    else:
        logging.info("ℹ️  Drone video streaming disabled in configuration")

    repo = TelemetryRepository()
    publisher = TelemetryPublisher(
        mqtt_client=mqtt,
    )

    # Initialize orchestrator with video stream
    orch = Orchestrator(drone, maps, analyzer, mqtt, video, repo, publisher)

    try:
        if start_lat and start_lon and dest_lat and dest_lon:
            # Use coordinates directly from dashboard
            from drone.models import Coordinate

            start = Coordinate(
                lat=float(start_lat), lon=float(start_lon), alt=float(start_alt)
            )
            dest = Coordinate(
                lat=float(dest_lat), lon=float(dest_lon), alt=float(dest_alt)
            )
            logging.info(
                f"Using coordinates from dashboard: Start ({start.lat}, {start.lon}) -> End ({dest.lat}, {dest.lon})"
            )
            await orch.run(start, dest, alt=float(dest_alt))
        else:
            logging.warning(
                "No flight coordinates provided - drone connection will not be established"
            )
            logging.info(
                "To start a flight, provide coordinates via command line or dashboard"
            )

    except ConnectionError as e:
        logging.error(f"❌ Connection error: {e}")
        logging.error("Please check:")
        logging.error(f"  1. Connection string: {settings.drone_conn}")
        logging.error("  2. Is the drone/autopilot powered on?")
        logging.error("  3. Is MAVProxy/SITL running (for TCP connections)?")
        logging.error("  4. Check network/firewall settings")
        raise
    except KeyboardInterrupt:
        logging.info("\n🛑 Manual abort - triggering safe shutdown")
        orch._running = False
    except Exception as e:
        logging.error(f"❌ Flight failed: {e}", exc_info=True)
    finally:
        await close_db()


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Drone Control System")
    parser.add_argument("--start-lat", type=float, help="Start latitude")
    parser.add_argument("--start-lon", type=float, help="Start longitude")
    parser.add_argument(
        "--start-alt", type=float, default=35.0, help="Start altitude (default: 35.0)"
    )
    parser.add_argument("--dest-lat", type=float, help="Destination latitude")
    parser.add_argument("--dest-lon", type=float, help="Destination longitude")
    parser.add_argument(
        "--dest-alt",
        type=float,
        default=35.0,
        help="Destination altitude (default: 35.0)",
    )
    parser.add_argument("--user-id", type=int, help="User ID for flight tracking")

    args = parser.parse_args()

    try:
        asyncio.run(
            main(
                start_lat=args.start_lat,
                start_lon=args.start_lon,
                start_alt=args.start_alt,
                dest_lat=args.dest_lat,
                dest_lon=args.dest_lon,
                dest_alt=args.dest_alt,
                user_id=args.user_id,
            )
        )
    except KeyboardInterrupt:
        logging.info("\n✅ Program terminated safely")
