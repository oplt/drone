from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

_TRUTHY_TOKENS = {"1", "true", "yes", "on"}
_FALSEY_TOKENS = {"0", "false", "no", "off", ""}


def env_truthy(value: str | bool | int | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value or "").strip().lower() in _TRUTHY_TOKENS


def env_falsey(value: str | bool | int | None) -> bool:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value == 0
    return str(value or "").strip().lower() in _FALSEY_TOKENS


class DailyDateFileHandler(logging.Handler):
    """
    File handler that writes to a source-specific runtime log directory and rolls over at day
    change.
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
        now = time.monotonic()
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


class DefaultLogRecordFieldsFilter(logging.Filter):
    """Ensure structured log formatters can always render trace/service fields."""

    _DEFAULTS = {
        "service_name": os.getenv("OTEL_SERVICE_NAME") or os.getenv("OTEL_SERVICE_NAME_OVERRIDE") or "drone-api",
        "environment": os.getenv("OTEL_ENVIRONMENT") or os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "local",
        "otel_trace_id": "",
        "otel_span_id": "",
        "trace_id": "",
        "span_id": "",
        "request_id": "",
        "correlation_id": "",
        "job_id": "",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self._DEFAULTS.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def _normalize_log_level(log_level: str | int) -> int:
    if isinstance(log_level, int):
        return log_level
    value = str(log_level or "INFO").strip()
    if value.isdigit():
        return int(value)
    return int(getattr(logging, value.upper(), logging.INFO))


def _ensure_filter(handler: logging.Handler, filter_type: type[logging.Filter]) -> None:
    if not any(isinstance(item, filter_type) for item in handler.filters):
        handler.addFilter(filter_type())


def _make_formatter(log_format: str) -> logging.Formatter:
    if str(log_format or "text").strip().lower() == "json":
        try:
            from pythonjsonlogger import jsonlogger

            return jsonlogger.JsonFormatter(
                (
                    "%(asctime)s %(levelname)s %(name)s %(message)s "
                    "%(service_name)s %(environment)s %(trace_id)s %(span_id)s "
                    "%(request_id)s %(correlation_id)s %(job_id)s"
                ),
                rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            )
        except ImportError:
            pass
    return logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(service_name)s | "
        "%(environment)s | trace=%(trace_id)s span=%(span_id)s | "
        "req=%(request_id)s corr=%(correlation_id)s job=%(job_id)s | %(message)s"
    )


def setup_logging(
    log_level: str | int = "INFO",
    log_file: Path | None = None,
    log_format: str = "json",
) -> None:
    """Centralized logging configuration with environment variable support"""
    from backend.core.logging.paths import runtime_log_dir

    level = _normalize_log_level(log_level)
    log_dir = (log_file.parent if log_file else runtime_log_dir("backend")).resolve()

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
                _ensure_filter(handler, DefaultLogRecordFieldsFilter)
        elif isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            has_stream_handler = True
            handler.setLevel(level)
            handler.setFormatter(formatter)
            _ensure_filter(handler, DefaultLogRecordFieldsFilter)

    if not has_daily_file_handler:
        file_handler = DailyDateFileHandler(log_dir=log_dir)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        _ensure_filter(file_handler, DefaultLogRecordFieldsFilter)
        root_logger.addHandler(file_handler)

    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        _ensure_filter(stream_handler, DefaultLogRecordFieldsFilter)
        root_logger.addHandler(stream_handler)

    try:
        from backend.observability.logging import install_trace_context_filter

        install_trace_context_filter()
    except Exception:
        pass

    logging.captureWarnings(True)

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
    mission_telemetry_startup_grace_s: float = Field(default=1.0, ge=0.0)

    patrol_sensor_trigger_geofence_tolerance_m: float = Field(default=75.0, ge=0.0, le=500.0)

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

    # Outdoor weather preflight (Open-Meteo + optional KMI/RMI for Belgium)
    weather_preflight_enabled: bool = True
    weather_cache_ttl_s: float = 300.0
    weather_api_fail_policy: str = "warn"  # warn | block | skip
    WIND_MAX: float = 12.0
    GUST_MAX: float = 15.0
    weather_max_precip_mm: float = 0.5
    weather_min_visibility_m: float = 3000.0
    weather_max_cloud_cover_pct: float = 90.0
    weather_min_temp_c: float = -10.0
    weather_max_temp_c: float = 40.0
    weather_blocked_codes: str = "45,48,56,57,65,67,75,77,82,85,86,95,96,99"
    weather_warn_codes: str = "51,53,55,61,63,80,81"
    kmi_rmi_validation_enabled: bool = True
    kmi_rmi_max_obs_age_hours: float = 6.0
    kmi_rmi_wind_delta_warn_mps: float = 4.0
    kmi_rmi_wind_delta_block_mps: float = 8.0
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    kmi_rmi_wfs_base_url: str = "https://opendata.meteo.be/service/aws/ows"

    # Video streaming configuration
    drone_video_source: str = "rtsp://192.168.4.1:8554/stream"
    drone_video_source_gazebo: str = Field(
        default="udp://127.0.0.1:5600",
        validation_alias=AliasChoices(
            "DRONE_VIDEO_SOURCE_SIM",
            "DRONE_VIDEO_SOURCE_GAZEBO",
        ),
    )
    drone_video_use_gazebo: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DRONE_VIDEO_USE_SIM",
            "DRONE_VIDEO_USE_GAZEBO",
        ),
    )
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

    # Warehouse perception bridge removed; fields remain only for backward-compatible settings.
    WAREHOUSE_BRIDGE_FLOW: str = "disabled"
    WAREHOUSE_ROS_BRIDGE_URL: str = ""
    WAREHOUSE_ROS_WS_URL: str = ""
    WAREHOUSE_ROS_CAPTURE_ROOT: str = "backend/storage/warehouse"
    WAREHOUSE_ROS_BRIDGE_TIMEOUT_S: float = 3.0
    WAREHOUSE_ROS_BRIDGE_DEEP_TIMEOUT_S: float = 90.0
    WAREHOUSE_ODOMETRY_STATE_PATH: str = ""
    WAREHOUSE_CAPTURE_ARTIFACT_WAIT_S: float = 45.0
    WAREHOUSE_SCAN_POSTPROCESS_CMD: str = ""
    ROS_DISTRO: str = "jazzy"
    WAREHOUSE_ROS_SETUP_FILE: str = "/opt/ros/jazzy/setup.bash"
    WAREHOUSE_ROS_WORKSPACE_SETUP_FILE: str = (
        "/home/polat/Desktop/Projects/drone_app/ros2_ws/install/setup.bash"
    )
    WAREHOUSE_NVBLOX_LAUNCH_PACKAGE: str = "drone_gz_bridge"
    WAREHOUSE_NVBLOX_LAUNCH_FILE: str = "warehouse_nvblox.launch.py"
    WAREHOUSE_NVBLOX_LAUNCH_ARGS: str = (
        "use_sim_time:=true "
        "run_rviz:=false "
        "start_odom_to_tf:=false "
        "start_odom_to_pose:=false "
        "use_tf_transforms:=true "
        "use_topic_transforms:=false "
        "input_qos:=SENSOR_DATA "
        "global_frame:=odom "
        "pose_frame:=iris_with_standoffs/base_link "
        "use_lidar:=true"
    )

    # Observability
    log_format: str = "json"  # "json" | "text"
    otel_enabled: bool = True
    otel_endpoint: str = ""
    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4318"
    otel_exporter_otlp_traces_endpoint: str = ""
    otel_exporter_otlp_metrics_endpoint: str = ""
    otel_exporter_otlp_logs_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""
    otel_metric_export_interval_ms: int = 30000
    otel_resource_attributes: str = "service.namespace=drone,service.version=local"
    otel_service_name: str = "drone-api"
    app_env: str = "local"
    grafana_public_url: str = ""
    prometheus_public_url: str = ""
    tempo_public_url: str = ""
    grafana_fleet_dashboard_path: str = "/d/drone-fleet/fleet-health"
    grafana_api_dashboard_path: str = "/d/drone-api/api-observability"
    grafana_workers_dashboard_path: str = "/d/drone-workers/worker-observability"
    grafana_video_dashboard_path: str = "/d/drone-video/video-pipeline"
    grafana_mavlink_dashboard_path: str = "/d/drone-mavlink/mavlink-telemetry"
    observability_health_timeout_s: float = 1.5
    observability_status_cache_ttl_s: float = 25.0

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

    # App flags
    debug_routes_enabled: bool = False
    db_auto_create: bool = False

    # Runtime logging
    drone_runtime_log_root: str = ""
    drone_runtime_log_retention_days: int = 14
    runtime_log_cleanup_interval_s: int = 86400

    # Celery worker
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = ""
    celery_default_queue: str = "default"
    celery_warehouse_mapping_queue: str = "warehouse-mapping"
    celery_video_analysis_queue: str = "video-analysis"
    celery_worker_max_tasks_per_child: int = 5
    celery_photogrammetry_time_limit_seconds: int = 6 * 60 * 60
    celery_photogrammetry_soft_time_limit_seconds: int = 5 * 60 * 60 + 30 * 60
    celery_enable_native_async_task: bool = False

    # Photogrammetry runtime (additional)
    photogrammetry_public_static_assets: bool = True
    photogrammetry_drone_sync_allow_absolute_source: bool = False
    photogrammetry_flight_sync_timeout_s: float = 120.0
    photogrammetry_flight_sync_poll_s: float = 2.0
    photogrammetry_flight_sync_min_images: int = 1
    photogrammetry_capture_sync_cmd: str = ""
    photogrammetry_capture_sync_timeout_s: float = 180.0
    photogrammetry_max_upload_files: int = 5000
    photogrammetry_max_upload_file_bytes: int = 1024 * 1024 * 1024
    photogrammetry_allowed_image_extensions: str = ".jpg,.jpeg,.png,.tif,.tiff,.webp"
    photogrammetry_processor_backend: str = "auto"
    photogrammetry_webodm_downloads_dir: str = "backend/storage/webodm_downloads"

    # WebODM client (additional)
    webodm_mock_outputs_dir: str = "backend/mock/webodm_outputs"
    webodm_http_timeout_s: float = 120.0
    webodm_http_retry_attempts: int = 5
    webodm_http_retry_min_delay_s: float = 4.0
    webodm_http_retry_max_delay_s: float = 60.0
    webodm_http_retry_backoff_factor: float = 2.0
    webodm_upload_batch_size: int = 256
    webodm_download_all_endpoint_template: str = (
        "/api/projects/{project_id}/tasks/{task_id}/download/all.zip"
    )
    webodm_poll_interval_s: float = 5.0
    webodm_poll_max_interval_s: float = 30.0

    # ROS
    ros_domain_id: str = "0"

    # Warehouse runtime (additional)
    warehouse_ros2_ws: str = "ros2_ws"
    warehouse_bridge_startup_grace_s: float = 3.0
    warehouse_live_map_ingest_token: str = "dev-live-map-ingest"
    warehouse_deep_health_probe_interval_s: float = 5.0
    warehouse_drone_sync_dir: str = "backend/storage/warehouse_captures"
    warehouse_drone_capture_staging_dir: str = ""
    warehouse_capture_sync_timeout_s: float = 120.0
    warehouse_capture_sync_poll_s: float = 2.0
    warehouse_capture_sync_min_files: int = 1
    warehouse_capture_sync_cmd: str = ""
    warehouse_capture_sync_cmd_timeout_s: float = 180.0
    warehouse_live_map_max_preview_points: int = 1500
    warehouse_live_map_poll_s: float = 0.5
    warehouse_live_map_pointcloud_every_n: int = 2
    warehouse_live_map_publish: bool = True
    warehouse_live_map_chunk_dir: str = "backend/storage/warehouse-live-map"
    warehouse_include_raw_lidar_preview: bool = False
    warehouse_persist_raw_lidar_layer: bool = False
    warehouse_preferred_map_layer: str = "rgbd_colored"
    warehouse_live_map_preferred_layer: str = "rgbd_colored"
    warehouse_live_map_raw_lidar_enabled: bool = True
    warehouse_live_map_raw_lidar_max_hz: float = 0.5
    warehouse_live_map_raw_lidar_voxel_size: float = 0.15
    warehouse_live_map_raw_lidar_max_points: int = 8000
    warehouse_live_map_frontend_max_concurrent_chunk_downloads: int = 8
    warehouse_live_map_frontend_max_points_per_layer: int = 800_000
    warehouse_require_rgb_for_save: bool = True
    warehouse_drone_video_source: str = ""
    warehouse_drone_video_use_gazebo: bool = False
    warehouse_video_recording_enabled: bool = True
    warehouse_disable_video: bool = False
    warehouse_bridge_topic_probe_attempts: int = 6
    warehouse_bridge_topic_probe_pause_s: float = 2.0
    warehouse_nvblox_boot_grace_s: float = 2.0
    warehouse_shutdown_mapping_stack_cmd: str = ""
    warehouse_sim_mode: bool = False
    warehouse_gazebo_sim: bool = False
    warehouse_ros_profile: str = ""
    warehouse_esdf_topic: str = ""
    warehouse_max_indoor_altitude_m: float = 6.0
    warehouse_takeoff_readiness_wait_s: float = 10.0
    warehouse_flight_mapping_wait_s: float = 45.0
    warehouse_mapping_warmup_rgbd_timeout_s: float = 45.0
    warehouse_preflight_tf_wait_s: float = 8.0
    # Warm the nvblox mapping stack in the background as soon as warehouse
    # preflight runs, so its ~20s init overlaps preflight/arming instead of
    # blocking the pre-takeoff critical path. The mission reuses the warm stack.
    warehouse_preflight_warm_nvblox: bool = True
    warehouse_preflight_warm_rgbd: bool = True
    warehouse_rgbd_readiness_cache_ttl_s: float = 30.0
    warehouse_preflight_report_cache_ttl_s: float = 4.0
    warehouse_preflight_snapshot_cache_ttl_s: float = 4.0
    warehouse_mapping_worker_probe_cache_ttl_s: float = 20.0
    structure_extraction_celery_probe_interval_s: float = 3.0
    warehouse_live_map_topic_probe_cache_ttl_s: float = 15.0
    warehouse_live_map_diagnostics_cache_ttl_s: float = 45.0
    warehouse_live_map_snapshot_cache_ttl_s: float = 120.0
    warehouse_live_map_clock_stability_s: float = 4.0
    warehouse_mapping_stack_preflight_clock_s: float = 4.0
    warehouse_nvblox_tf_restart_jump_threshold: int = 5
    warehouse_nvblox_tf_restart_cooldown_s: float = 60.0
    warehouse_preflight_wait_nvblox: bool = False
    warehouse_scan_require_nvblox_ready: bool = True

    # Automatic warehouse structure extraction (3D map -> aisles/racks/shelves/bins).
    # Runs as a post-flight Celery job; tunables drive the geometry heuristics and
    # the clearance gate applied to every auto-generated scan pose.
    warehouse_structure_extraction_enabled: bool = True
    warehouse_structure_voxel_m: float = 0.05
    warehouse_structure_grid_res_m: float = 0.10
    warehouse_structure_floor_margin_m: float = 0.15
    warehouse_structure_ceiling_max_m: float = 8.0
    warehouse_structure_min_aisle_width_m: float = 0.9
    warehouse_structure_min_rack_length_m: float = 0.6
    warehouse_structure_bin_pitch_m: float = 0.9
    warehouse_structure_shelf_min_spacing_m: float = 0.3
    warehouse_structure_max_shelf_levels: int = 6
    warehouse_structure_max_bins_per_rack_face: int = 8
    warehouse_structure_min_target_spacing_m: float = 0.75
    warehouse_structure_review_clearance_m: float = 0.10
    warehouse_structure_standoff_m: float = 1.2
    warehouse_structure_drone_radius_m: float = 0.35
    warehouse_structure_clearance_margin_m: float = 0.25
    warehouse_structure_max_points: int = 6_000_000

    # Simulation / indoor navigation flags
    sim_mode: bool = False
    indoor_nav: bool = False

    # Irrigation
    irrigation_storage_dir: str = "backend/storage/irrigation"
    irrigation_capture_interval_s: float = 1.5
    irrigation_camera_fov_h_deg: float = 78.0
    irrigation_camera_fov_v_deg: float = 62.0
    irrigation_monitor_poll_s: float = 10.0

    # Video analysis
    video_analysis_upload_dir: str = "backend/storage/video_analysis/uploads"
    video_analysis_max_upload_bytes: int = 1024 * 1024 * 1024

    # Mission / preflight TTL
    preflight_run_ttl_seconds: int = 900
    require_preflight_run_before_mission: bool = False
    allow_warn_preflight_start: bool = True
    mission_runtime_ttl_seconds: int = 86400
    mission_runtime_max_history: int = 200

    # Background cleanup
    preflight_cleanup_interval_s: int = 300
    mission_cleanup_interval_s: int = 3600
    mission_runtime_retention_days: int = 30
    telemetry_cleanup_interval_s: int = 21600
    telemetry_raw_retention_days: int = 90
    telemetry_summary_retention_days: int = 365
    mavlink_retention_days: int = 14
    telemetry_cleanup_batch: int = 10000

    @model_validator(mode="after")
    def _default_celery_result_backend(self) -> RuntimeSettings:
        if not self.celery_result_backend:
            self.celery_result_backend = self.celery_broker_url
        return self


settings = RuntimeSettings()
