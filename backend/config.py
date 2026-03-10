from pathlib import Path
import logging
import threading
from datetime import datetime
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class DailyDateFileHandler(logging.Handler):
    """
    File handler that writes to backend/logs/YYYY-MM-DD.log and rolls over at day change.
    """

    def __init__(self, log_dir: Path, *, encoding: str = "utf-8") -> None:
        super().__init__()
        self.log_dir = log_dir.resolve()
        self.encoding = encoding
        self._current_day: str | None = None
        self._file_handler: logging.FileHandler | None = None
        self._lock = threading.RLock()

    @staticmethod
    def _today_token() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _build_log_path(self, day_token: str) -> Path:
        return self.log_dir / f"{day_token}.log"

    def _ensure_handler(self) -> None:
        day_token = self._today_token()
        if self._file_handler is not None and self._current_day == day_token:
            return

        self.log_dir.mkdir(parents=True, exist_ok=True)
        if self._file_handler is not None:
            self._file_handler.close()
            self._file_handler = None

        file_handler = logging.FileHandler(
            self._build_log_path(day_token),
            encoding=self.encoding,
        )
        file_handler.setLevel(self.level)
        if self.formatter is not None:
            file_handler.setFormatter(self.formatter)
        self._file_handler = file_handler
        self._current_day = day_token

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            try:
                self._ensure_handler()
                if self._file_handler is not None:
                    self._file_handler.emit(record)
            except Exception:
                self.handleError(record)

    def setFormatter(self, fmt: logging.Formatter) -> None:
        with self._lock:
            super().setFormatter(fmt)
            if self._file_handler is not None:
                self._file_handler.setFormatter(fmt)

    def setLevel(self, level: int | str) -> None:
        with self._lock:
            super().setLevel(level)
            if self._file_handler is not None:
                self._file_handler.setLevel(level)

    def close(self) -> None:
        with self._lock:
            try:
                if self._file_handler is not None:
                    self._file_handler.close()
                    self._file_handler = None
            finally:
                super().close()


def setup_logging(log_level: str | int = "INFO", log_file: Path | None = None) -> None:
    """Centralized logging configuration with environment variable support"""
    level = (
        log_level
        if isinstance(log_level, int)
        else getattr(logging, log_level, logging.INFO)
    )
    log_dir = (log_file.parent if log_file else (BASE_DIR / "logs")).resolve()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    has_daily_file_handler = False
    has_stream_handler = False

    for handler in root_logger.handlers:
        if isinstance(handler, DailyDateFileHandler):
            if handler.log_dir == log_dir:
                has_daily_file_handler = True
                handler.setLevel(level)
                handler.setFormatter(formatter)
        elif isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            has_stream_handler = True
            handler.setLevel(level)
            handler.setFormatter(formatter)

    if not has_daily_file_handler:
        file_handler = DailyDateFileHandler(log_dir=log_dir)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)


class BootstrapSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str
    settings_vault_key: str

bootstrap = BootstrapSettings()


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str

    google_maps_api_key: str
    llm_provider: str = "ollama"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    mqtt_use_tls: bool = False
    mqtt_ca_certs: str = ""

    opcua_endpoint: str = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
    opcua_security_policy: str = "Basic256Sha256"
    opcua_cert_path: str = ""
    opcua_key_path: str = ""

    telem_log_interval_sec: float = 2.0
    telemetry_topic: str = "ardupilot/telemetry"

    drone_conn: str
    drone_conn_mavproxy: str


    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 60
    admin_emails: str = ""
    admin_domains: str = ""

    raspberry_ip: str
    raspberry_user: str
    raspberry_host: str
    raspberry_password: str
    raspberry_streaming_script_path: str = "/home/polat/drone_cam/pi_camera_server.py"
    ssh_key_path: str

    battery_capacity_wh: float = 77
    cruise_power_w: float = 180
    cruise_speed_mps: float = 8
    energy_reserve_frac: float = 0.2
    heartbeat_timeout: float
    enforce_preflight_range: bool = False

    # Operational alert/rules engine
    alerts_enabled: bool = True
    alerts_check_interval_sec: int = 5
    alerts_dedupe_window_sec: int = 300
    alerts_operation_geofence_id: int | None = None
    alerts_monitor_herd_ids: str = ""
    alerts_herd_isolation_threshold_m: float = 250.0
    alerts_low_battery_percent: float = 25.0
    alerts_weak_link_percent: float = 35.0
    alerts_high_wind_mps: float = 12.0
    alerts_route_in_app: bool = True
    alerts_route_email: bool = False
    alerts_route_sms: bool = False
    alerts_email_recipients: str = ""
    alerts_sms_recipients: str = ""
    alerts_smtp_host: str = ""
    alerts_smtp_port: int = 587
    alerts_smtp_user: str = ""
    alerts_smtp_password: str = ""
    alerts_smtp_from: str = ""
    alerts_smtp_use_tls: bool = True
    alerts_twilio_account_sid: str = ""
    alerts_twilio_auth_token: str = ""
    alerts_twilio_from_number: str = ""

    # Preflight thresholds (override defaults at runtime via /api/settings)
    HDOP_MAX: float = 2.0
    SAT_MIN: int = 10
    HOME_MAX_DIST: float = 30.0
    GPS_FIX_TYPE_MIN: int = 3
    EKF_THRESHOLD: float = 0.8
    COMPASS_HEALTH_REQUIRED: bool = True
    BATTERY_MIN_V: float = 0.0
    BATTERY_MIN_PERCENT: float = 20.0
    HEARTBEAT_MAX_AGE: float = 3.0
    MSG_RATE_MIN_HZ: float = 2.0
    RTL_MIN_ALT: float = 15.0
    MIN_CLEARANCE: float = 3.0
    AGL_MIN: float = 5.0
    AGL_MAX: float = 120.0
    MAX_RANGE_M: float = 1500.0
    MAX_WAYPOINTS: int = 60
    NFZ_BUFFER_M: float = 15.0
    A_LAT_MAX: float = 3.0
    BANK_MAX_DEG: float = 30.0
    TURN_PENALTY_S: float = 2.0
    WP_RADIUS_M: float = 2.0

    # Video streaming configuration
    drone_video_source: str = "rtsp://192.168.4.1:8554/stream"
    drone_video_source_gazebo: str = "udp://127.0.0.1:5600"
    drone_video_use_gazebo: bool = False
    drone_video_enabled: bool = True
    drone_video_width: int = 640
    drone_video_height: int = 480
    drone_video_fps: int = 30
    drone_video_timeout: float = 10.0
    drone_video_fallback: str = ""
    drone_video_save_stream: bool = False
    drone_video_save_path: str = "./backend/video/recordings/"

    # Wireless streaming network configuration
    drone_video_wifi_ssid: str = "Drone_Network"
    drone_video_wifi_password: str = "drone123"

    # Photogrammetry pipeline/runtime parameters
    PHOTOGRAMMETRY_DRONE_SYNC_DIR: str = "backend/storage/drone_sync"
    PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR: str = "backend/storage/staging"
    PHOTOGRAMMETRY_INPUTS_DIR: str = "backend/storage/mapping_jobs_inputs"
    PHOTOGRAMMETRY_STORAGE_DIR: str = "backend/storage/mapping"
    PHOTOGRAMMETRY_STORAGE_BASE_URL: str = "/mapping-assets"
    PHOTOGRAMMETRY_3DTILES_CMD: str = ""
    PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET: bool = False
    WEBODM_BASE_URL: str =""
    WEBODM_API_TOKEN: str = ""
    WEBODM_PROJECT_ID: int = 1
    WEBODM_MOCK_MODE: bool = False
    MAPPING_JOB_QUEUE_BACKEND: str = "celery"
    CELERY_PHOTOGRAMMETRY_QUEUE: str = "photogrammetry"
    PHOTOGRAMMETRY_ASSET_SIGNING_SECRET: str = ""



settings = RuntimeSettings()
