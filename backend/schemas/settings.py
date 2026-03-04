from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class TelemetrySettings(BaseModel):
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: Optional[str] = None  # SECRET (vault); masked in GET
    mqtt_use_tls: bool = False
    mqtt_ca_certs: str = ""
    opcua_endpoint: str = ""
    opcua_security_policy: str = ""
    opcua_cert_path: str = ""
    opcua_key_path: str = ""
    telem_log_interval_sec: int = 2
    telemetry_topic: str = "ardupilot/telemetry"


class AISettings(BaseModel):
    llm_provider: str = "ollama"
    llm_api_base: str = ""
    llm_model: str = ""
    llm_api_key: Optional[str] = None  # SECRET (vault); masked in GET


class CredentialsSettings(BaseModel):
    google_maps_api_key: str = ""  # you currently treat as non-secret (kept in DB JSON)
    drone_conn: str = ""
    admin_emails: str = ""
    admin_domains: str = ""


class HardwareSettings(BaseModel):
    battery_capacity_wh: float = 77.0
    energy_reserve_frac: float = 0.2
    cruise_speed_mps: float = 8.0
    cruise_power_w: float = 180.0
    heartbeat_timeout: float = 5.0
    enforce_preflight_range: bool = False


class PreflightSettings(BaseModel):
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


class RaspberrySettings(BaseModel):
    raspberry_ip: str = ""
    raspberry_user: str = ""
    raspberry_host: str = ""
    raspberry_password: Optional[str] = None  # SECRET (vault); masked in GET
    ssh_key_path: str = ""
    raspberry_streaming_script_path: str = ""


class CameraSettings(BaseModel):
    drone_video_source: str = ""
    drone_video_source_gazebo: str = "udp://127.0.0.1:5600"
    drone_video_use_gazebo: bool = False
    drone_video_width: int = 640
    drone_video_height: int = 480
    drone_video_fps: int = 30
    drone_video_timeout: float = 10.0
    drone_video_save_path: str
    drone_video_fallback: str = ""
    drone_video_enabled: bool = True
    drone_video_save_stream: bool = False


class PhotogrammetrySettings(BaseModel):
    PHOTOGRAMMETRY_DRONE_SYNC_DIR: str = "backend/storage/drone_sync"
    PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR: str = "backend/storage/staging"
    PHOTOGRAMMETRY_INPUTS_DIR: str = "backend/storage/mapping_jobs_inputs"
    PHOTOGRAMMETRY_STORAGE_DIR: str = "backend/storage/mapping"
    PHOTOGRAMMETRY_STORAGE_BASE_URL: str = "/mapping-assets"
    PHOTOGRAMMETRY_3DTILES_CMD: str = ""
    PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET: bool = False
    WEBODM_BASE_URL: str = "http://localhost:8001"
    WEBODM_API_TOKEN: Optional[str] = None  # SECRET (vault); masked in GET
    WEBODM_PROJECT_ID: int = 1
    WEBODM_MOCK_MODE: bool = False
    MAPPING_JOB_QUEUE_BACKEND: str = "celery"
    CELERY_PHOTOGRAMMETRY_QUEUE: str = "photogrammetry"
    PHOTOGRAMMETRY_ASSET_SIGNING_SECRET: Optional[str] = None  # SECRET (vault); masked in GET


class SettingsDoc(BaseModel):
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    ai: AISettings = Field(default_factory=AISettings)
    credentials: CredentialsSettings = Field(default_factory=CredentialsSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    preflight: PreflightSettings = Field(default_factory=PreflightSettings)
    raspberry: RaspberrySettings = Field(default_factory=RaspberrySettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)
    photogrammetry: PhotogrammetrySettings = Field(default_factory=PhotogrammetrySettings)
    updated_at: Optional[str] = None
