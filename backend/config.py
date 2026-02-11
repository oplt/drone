from dotenv import load_dotenv
import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


def setup_logging():
    """Centralized logging configuration with environment variable support"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",  # Added module name
        handlers=[logging.FileHandler("drone.log"), logging.StreamHandler()],
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    google_maps_api_key: str
    llm_provider: str = "ollama"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""

    opcua_endpoint: str = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
    drone_conn: str = "tcp:127.0.0.1:5760"
    drone_conn_mavproxy: str = "tcp:127.0.0.1:5760"

    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/drone_db"

    telem_log_interval_sec: float = 2.0
    telemetry_topic: str = "ardupilot/telemetry"

    heartbeat_timeout: float = 5.0

    enforce_preflight_range: bool = False

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 60

    rasperry_ip: str
    rasperry_user: str
    rasperry_host: str
    rasperry_password: str
    rasperry_streaming_script_path: str = "/home/polat/drone_cam/pi_camera_server.py"
    ssh_key_path: str

    battery_capacity_wh: float = 77
    cruise_power_w: float = 180
    cruise_speed_mps: float = 8
    energy_reserve_frac: float = 0.2

    # Video streaming configuration for wireless drone connection
    drone_video_source: str = (
        "rtsp://192.168.4.1:8554/stream"  # Wireless RTSP stream from drone
    )
    drone_video_enabled: bool = True  # Enable video streaming by default
    drone_video_width: int = 640  # Standard VGA resolution
    drone_video_height: int = 480  # Standard VGA resolution
    drone_video_fps: int = 30  # 30 FPS for smooth video
    drone_video_timeout: float = 10.0  # 10 second timeout for wireless connection
    drone_video_fallback: str = ""  # No fallback file by default
    drone_video_save_stream: bool = False  # Disable recording by default
    drone_video_save_path: str = "./recordings/"  # Local recordings directory

    # Wireless streaming network configuration
    drone_video_network_mode: str = (
        "rtsp"  # Streaming protocol: "rtsp", "http", "webrtc"
    )
    drone_video_network_ip: str = "192.168.4.1"  # Drone's WiFi IP address
    drone_video_network_port: int = 8080  # HTTP web interface port
    drone_video_rtsp_port: int = 8554  # RTSP streaming port
    drone_video_wifi_ssid: str = "Drone_Network"  # Drone's WiFi network name
    drone_video_wifi_password: str = "drone123"  # Drone's WiFi password


settings = Settings()
