from pathlib import Path
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent



def setup_logging(log_level: str | int = "INFO", log_file: Path | None = None) -> None:
    """Centralized logging configuration with environment variable support"""
    level = (
        log_level
        if isinstance(log_level, int)
        else getattr(logging, log_level, logging.INFO)
    )
    log_path = (log_file or (BASE_DIR.parent / "drone.log")).resolve()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    has_file_handler = False
    has_stream_handler = False

    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            existing_path = Path(getattr(handler, "baseFilename", "")).resolve()
            if existing_path == log_path:
                has_file_handler = True
        elif isinstance(handler, logging.StreamHandler):
            has_stream_handler = True

    if not has_file_handler:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,  # This helps with case-insensitive env vars
    )

    google_maps_api_key: str
    llm_provider: str = "ollama"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    mqtt_use_tls: bool = True
    mqtt_ca_certs: str = ""

    opcua_endpoint: str = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
    opcua_security_policy: str = "Basic256Sha256"
    opcua_cert_path: str = ""
    opcua_key_path: str = ""
    drone_conn: str
    drone_conn_mavproxy: str

    database_url: str

    telem_log_interval_sec: float = 2.0
    telemetry_topic: str = "ardupilot/telemetry"

    heartbeat_timeout: float

    enforce_preflight_range: bool = False

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 60
    admin_emails: str = ""
    admin_domains: str = ""

    # Note: These have typos - 'rasperry' instead of 'raspberry'
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

    # Video streaming configuration
    drone_video_source: str = "rtsp://192.168.4.1:8554/stream"
    drone_video_enabled: bool = True
    drone_video_width: int = 640
    drone_video_height: int = 480
    drone_video_fps: int = 30
    drone_video_timeout: float = 10.0
    drone_video_fallback: str = ""
    drone_video_save_stream: bool = False
    drone_video_save_path: str = "./recordings/"

    # Wireless streaming network configuration
    drone_video_network_mode: str = "rtsp"
    drone_video_network_ip: str = "192.168.4.1"
    drone_video_network_port: int = 8080
    drone_video_rtsp_port: int = 8554
    drone_video_wifi_ssid: str = "Drone_Network"
    drone_video_wifi_password: str = "drone123"

settings = Settings()
