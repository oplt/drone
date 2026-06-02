import logging
import threading
from datetime import datetime
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


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


class RepeatedAutopilotLogFilter(logging.Filter):
    """Suppress same autopilot identification line repeated during MAVLink handshakes."""

    def __init__(self, window_s: float = 2.0) -> None:
        super().__init__()
        self.window_s = window_s
        self._last_by_message: dict[str, float] = {}
        self._lock = threading.RLock()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "autopilot":
            return True
        message = record.getMessage()
        now = datetime.now().timestamp()
        with self._lock:
            last_at = self._last_by_message.get(message)
            if last_at is not None and now - last_at <= self.window_s:
                return False
            self._last_by_message = {
                cached: cached_at
                for cached, cached_at in self._last_by_message.items()
                if now - cached_at <= self.window_s
            }
            self._last_by_message[message] = now
        return True


def _make_formatter(log_format: str) -> logging.Formatter:
    if log_format == "json":
        try:
            from pythonjsonlogger import jsonlogger

            return jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            )
        except ImportError:
            pass
    return logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def setup_logging(
    log_level: str | int = "INFO",
    log_file: Path | None = None,
    log_format: str = "json",
) -> None:
    """Centralized logging configuration with environment variable support"""
    level = log_level if isinstance(log_level, int) else getattr(logging, log_level, logging.INFO)
    log_dir = (log_file.parent if log_file else (BASE_DIR / "logs")).resolve()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = _make_formatter(log_format)

    has_daily_file_handler = False
    has_stream_handler = False

    for handler in root_logger.handlers:
        if isinstance(handler, DailyDateFileHandler):
            if handler.log_dir == log_dir:
                has_daily_file_handler = True
                handler.setLevel(level)
                handler.setFormatter(formatter)
        elif isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
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

    autopilot_logger = logging.getLogger("autopilot")
    if not any(isinstance(item, RepeatedAutopilotLogFilter) for item in autopilot_logger.filters):
        autopilot_logger.addFilter(RepeatedAutopilotLogFilter())


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
        env_ignore_empty=True,
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
    jwt_access_exp_minutes: int = 15
    jwt_refresh_exp_days: int = 30
    cookie_secure: bool = False  # Set True in production with HTTPS
    cookie_domain: str = ""
    cookie_samesite: str = "lax"
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
    drone_video_save_stream: bool = True
    drone_video_save_path: str = "./backend/storage/video_records/"

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
    WEBODM_BASE_URL: str = ""
    WEBODM_API_TOKEN: str = ""
    WEBODM_PROJECT_ID: int = 1
    WEBODM_MOCK_MODE: bool = False
    MAPPING_JOB_QUEUE_BACKEND: str = "celery"
    CELERY_PHOTOGRAMMETRY_QUEUE: str = "photogrammetry"
    PHOTOGRAMMETRY_ASSET_SIGNING_SECRET: str = ""

    # Warehouse ROS 2 / Isaac perception bridge. The FastAPI backend talks to
    # this companion service; ROS nodes stay outside the API process.
    WAREHOUSE_ROS_BRIDGE_URL: str = "http://127.0.0.1:8088"
    WAREHOUSE_ROS_WS_URL: str = ""
    WAREHOUSE_ROS_CAPTURE_ROOT: str = "backend/storage/warehouse_ros"
    WAREHOUSE_ROS_PROFILE: str = "isaac_ros_nvblox_stereo"
    WAREHOUSE_ROS_BRIDGE_TIMEOUT_S: float = 3.0
    WAREHOUSE_ROS_BRIDGE_DEEP_TIMEOUT_S: float = 90.0
    WAREHOUSE_ODOMETRY_STATE_PATH: str = ""
    WAREHOUSE_CAPTURE_ARTIFACT_WAIT_S: float = 45.0
    WAREHOUSE_SCAN_POSTPROCESS_CMD: str = ""

    # Observability
    log_format: str = "json"  # "json" | "text"
    otel_enabled: bool = False
    otel_endpoint: str = ""

    # Shadow-mode: run old direct-DB-write path alongside new queued path so
    # both can be compared before fully removing the legacy write. Set to False
    # (disabled) once the queued path has proven stable in production.
    orchestrator_shadow_mode: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Google OIDC
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oidc_redirect_uri: str = ""

    # Object storage
    storage_backend: str = "local"  # "local" | "s3"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_name: str = "drone-assets"
    s3_region: str = "auto"
    s3_public_base_url: str = ""

    # Webhooks
    webhook_delivery_timeout_sec: int = 10
    webhook_max_retries: int = 5

    # Analytics cache
    analytics_cache_ttl_sec: int = 60


settings = RuntimeSettings()
