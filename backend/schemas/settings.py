from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class GeneralSettings(BaseModel):
    llm_provider: str = "ollama"
    llm_api_base: str = ""
    llm_model: str = ""

    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = ""

    telem_log_interval_sec: float = 2.0
    telemetry_topic: str = "ardupilot/telemetry"

    enforce_preflight_range: bool = False
    heartbeat_timeout: float = 5.0

    # secrets (masked on GET)
    llm_api_key: Optional[str] = None
    mqtt_pass: Optional[str] = None


class PreflightSettings(BaseModel):
    HDOP_MAX: float = 2.5
    SAT_MIN: int = 6
    HOME_MAX_DIST: float = 100.0
    HEARTBEAT_MAX_AGE: float = 3.0
    MSG_RATE_MIN_HZ: float = 5.0
    RTL_MIN_ALT: float = 30.0
    MIN_CLEARANCE: float = 5.0
    NFZ_BUFFER_M: float = 50.0
    COMPASS_HEALTH_REQUIRED: bool = True


class MissionSettings(BaseModel):
    cruise_speed_mps: float = 8.0
    cruise_power_w: float = 180.0
    battery_capacity_wh: float = 77.0
    energy_reserve_frac: float = 0.2

    AGL_MIN: float = 10.0
    AGL_MAX: float = 120.0
    MAX_RANGE_M: float = 5000.0
    MAX_WAYPOINTS: int = 700


class SettingsDoc(BaseModel):
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    preflight: PreflightSettings = Field(default_factory=PreflightSettings)
    mission: MissionSettings = Field(default_factory=MissionSettings)
    updated_at: Optional[str] = None