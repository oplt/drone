from dataclasses import dataclass
from dotenv import load_dotenv
import os
import logging

load_dotenv()

def setup_logging():
    """Centralized logging configuration with environment variable support"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",  # Added module name
        handlers=[
            logging.FileHandler("drone.log"),
            logging.StreamHandler()
        ]
    )

@dataclass
class Settings:
    google_maps_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    llm_api_base: str = os.getenv("LLM_API_BASE", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")

    mqtt_broker: str = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_user: str = os.getenv("MQTT_USER", "")
    mqtt_pass: str = os.getenv("MQTT_PASS", "")
    opcua_endpoint: str = os.getenv("OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/freeopcua/server/")
    drone_conn: str = os.getenv("DRONE_CONNECTION_SITL", "tcp:127.0.0.1:5760")
    # drone_conn: str = os.getenv("DRONE_CONNECTION_RASPI", "tcp:127.0.0.1:5760")
    drone_conn_mavproxy: str = os.getenv("DRONE_CONNECTION_STR_MAVPROXY", "tcp:127.0.0.1:5760")
    # If connecting to a networked drone:
    # "udp:192.168.0.10:14550" (IP/port from your drone's telemetry)


    telem_log_interval_sec: float = float(os.getenv("TELEMETRY_LOG_INTERVAL_SEC", "2"))
    telemetry_topic: str = "ardupilot/telemetry"

    # Video streaming configuration for wireless drone connection
    # drone_video_source: str = "rtsp://192.168.4.1:8554/stream"  # Wireless RTSP stream from drone
    drone_video_enabled: bool = True  # Enable video streaming by default
    drone_video_width: int = 640  # Standard VGA resolution
    drone_video_height: int = 480  # Standard VGA resolution
    drone_video_fps: int = 30  # 30 FPS for smooth video
    drone_video_timeout: float = 10.0  # 10 second timeout for wireless connection
    drone_video_fallback: str = ""  # No fallback file by default
    drone_video_save_stream: bool = True  # Disable recording by default
    drone_video_save_path: str = "./recordings/"  # Local recordings directory
    
    # Wireless streaming network configuration
    # drone_video_network_mode: str = "rtsp"  # Streaming protocol: "rtsp", "http", "webrtc"
    # drone_video_network_ip: str = "192.168.4.1"  # Drone's WiFi IP address
    # drone_video_network_port: int = 8080  # HTTP web interface port
    # drone_video_rtsp_port: int = 8554  # RTSP streaming port
    # drone_video_wifi_ssid: str = "Drone_Network"  # Drone's WiFi network name
    # drone_video_wifi_password: str = "drone123"  # Drone's WiFi password

    battery_capacity_wh: float = float(os.getenv("BATTERY_CAPACITY_WH", "77"))
    cruise_power_w: float = float(os.getenv("CRUISE_POWER_W", "180"))
    cruise_speed_mps: float = float(os.getenv("CRUISE_SPEED_MPS", "8"))
    energy_reserve_frac: float = float(os.getenv("ENERGY_RESERVE_FRAC", "0.2"))

    heartbeat_timeout : float = float(os.getenv("HEARTBEAT_TIMEOUT", "15"))  # Increased from 5s to 15s for initialization tolerance

    ENFORCE_PREFLIGHT_RANGE = os.getenv("ENFORCE_PREFLIGHT_RANGE", "true").lower() in {"1","true","yes","on"}

    rasperry_ip: str = os.getenv("RASPERRY_PI_IP")
    rasperry_user: str = os.getenv("RASPERRY_PI_USER", "pi")
    rasperry_host: str = "raspberrypi.local"
    rasperry_password: str = os.getenv("RASPERRY_PI_PASSWORD")
    rasperry_streaming_script_path: str = "/home/polat/drone_cam/pi_camera_server.py"
    ssh_key_path: str = os.getenv("SSH_KEY_PATH")
    raspberry_camera_enabled: bool = True
    rasperry_streaming_port: int = 5000

    # Database Pool Settings
    DB_POOL_SIZE: int = 20           # Number of connections to keep open
    DB_MAX_OVERFLOW: int = 10        # Max connections above pool_size
    DB_POOL_RECYCLE: int = 3600      # Recycle connections after 1 hour
    DB_POOL_TIMEOUT: int = 30        # Timeout for getting connection
    DB_POOL_PRE_PING: bool = True    # Verify connection before use
    DB_ECHO: bool = False            # Set to True for SQL debugging
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/drone_db")
    DB_OPTIMIZE_INTERVAL: int = 3600  # 1 hour - reduced frequency to avoid unnecessary load




settings = Settings()
