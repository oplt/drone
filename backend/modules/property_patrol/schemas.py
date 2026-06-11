from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PatrolMode = Literal["perimeter", "grid", "adaptive"]
CameraDirection = Literal["inward", "outward", "forward", "adaptive"]
TriggerBehavior = Literal["notify_only", "approval_required", "auto_dispatch"]
MissionRunType = Literal["scheduled", "sensor_triggered", "manual"]
SensorEventStatus = Literal["received", "validated", "rejected", "dispatched", "duplicate", "ignored"]
IncidentStatus = Literal["open", "acknowledged", "false_positive", "escalated", "closed"]

MISSION_STATES = {
    "DRAFT", "VALIDATED", "SCHEDULED", "PREFLIGHT_CHECK", "ARMED", "TAKEOFF",
    "PATROL", "INVESTIGATE_EVENT", "RETURN_HOME", "LANDING", "COMPLETED", "ABORTED",
    "PAUSED_BY_OPERATOR", "GEOFENCE_VIOLATION", "LOW_BATTERY_RTH", "LINK_LOST_RTH",
    "GPS_DEGRADED_HOLD", "AIRSPACE_BLOCKED", "SENSOR_TRIGGER_REJECTED", "FAILED",
}


class GeoPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    alt: float | None = None


class ValidationIssue(BaseModel):
    code: str
    message: str
    waypoint_index: int | None = None


class ValidationResult(BaseModel):
    ok: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class PropertyPatrolSiteBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    property_boundary: dict[str, Any]
    flight_safe_area: dict[str, Any]
    no_fly_zones: list[dict[str, Any]] = Field(default_factory=list)
    privacy_zones: list[dict[str, Any]] = Field(default_factory=list)
    emergency_landing_zones: list[dict[str, Any]] = Field(default_factory=list)
    default_home_position: GeoPoint | None = None
    default_altitude_m: float = Field(default=30.0, gt=0, le=120)


class PropertyPatrolSiteCreate(PropertyPatrolSiteBase):
    pass


class PropertyPatrolSiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    property_boundary: dict[str, Any] | None = None
    flight_safe_area: dict[str, Any] | None = None
    no_fly_zones: list[dict[str, Any]] | None = None
    privacy_zones: list[dict[str, Any]] | None = None
    emergency_landing_zones: list[dict[str, Any]] | None = None
    default_home_position: GeoPoint | None = None
    default_altitude_m: float | None = Field(default=None, gt=0, le=120)


class PropertyPatrolSiteOut(PropertyPatrolSiteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PatrolTemplateBase(BaseModel):
    site_id: int
    name: str = Field(min_length=1, max_length=160)
    patrol_mode: PatrolMode = "perimeter"
    altitude_m: float = Field(default=30.0, ge=5.0, le=120.0)
    speed_mps: float = Field(default=6.0, ge=0.5, le=20.0)
    boundary_offset_m: float = Field(default=15.0, ge=0.0, le=120.0)
    grid_spacing_m: float = Field(default=40.0, gt=1.0, le=300.0)
    overlap_percent: float = Field(default=50.0, ge=0.0, le=95.0)
    camera_direction: CameraDirection = "inward"
    camera_gimbal_pitch_deg: float = Field(default=35.0, ge=0.0, le=90.0)
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    max_mission_duration_minutes: int = Field(default=25, ge=1, le=180)
    min_battery_return_percent: float = Field(default=30.0, ge=10.0, le=80.0)
    trigger_behavior: TriggerBehavior = "approval_required"
    ai_detection_enabled: bool = True
    llm_summary_enabled: bool = False
    privacy_blur_faces: bool = True
    privacy_blur_license_plates: bool = True
    event_clip_recording_only: bool = True
    retention_hours_or_days: str = Field(default="72h", max_length=32)


class PatrolTemplateCreate(PatrolTemplateBase):
    pass


class PatrolTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    patrol_mode: PatrolMode | None = None
    altitude_m: float | None = Field(default=None, ge=5.0, le=120.0)
    speed_mps: float | None = Field(default=None, ge=0.5, le=20.0)
    boundary_offset_m: float | None = Field(default=None, ge=0.0, le=120.0)
    grid_spacing_m: float | None = Field(default=None, gt=1.0, le=300.0)
    overlap_percent: float | None = Field(default=None, ge=0.0, le=95.0)
    camera_direction: CameraDirection | None = None
    camera_gimbal_pitch_deg: float | None = Field(default=None, ge=0.0, le=90.0)
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    max_mission_duration_minutes: int | None = Field(default=None, ge=1, le=180)
    min_battery_return_percent: float | None = Field(default=None, ge=10.0, le=80.0)
    trigger_behavior: TriggerBehavior | None = None
    ai_detection_enabled: bool | None = None
    llm_summary_enabled: bool | None = None
    privacy_blur_faces: bool | None = None
    privacy_blur_license_plates: bool | None = None
    event_clip_recording_only: bool | None = None
    retention_hours_or_days: str | None = Field(default=None, max_length=32)


class PatrolTemplateOut(PatrolTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PatrolWaypoint(BaseModel):
    lat: float
    lon: float
    alt: float
    speed_mps: float | None = None
    yaw_deg: float | None = None
    camera_direction: str | None = None


class RoutePreviewIn(BaseModel):
    site_id: int
    template_id: int | None = None
    patrol_mode: PatrolMode | None = None
    altitude_m: float | None = None
    speed_mps: float | None = None
    boundary_offset_m: float | None = None
    grid_spacing_m: float | None = None
    overlap_percent: float | None = None
    camera_direction: CameraDirection | None = None
    camera_gimbal_pitch_deg: float | None = None


class RoutePreviewOut(BaseModel):
    waypoints: list[PatrolWaypoint]
    stats: dict[str, Any]
    validation: ValidationResult


class MissionValidateIn(RoutePreviewIn):
    route_waypoints: list[PatrolWaypoint] | None = None


class MissionStartIn(RoutePreviewIn):
    mission_type: MissionRunType = "manual"
    drone_id: str | None = None


class MissionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int | None = None
    site_id: int
    mission_type: str
    state: str
    route_waypoints: list[Any]
    start_time: datetime | None = None
    end_time: datetime | None = None
    drone_id: str | None = None
    operator_id: int | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class SensorEventCreate(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=160)
    external_event_id: str = Field(min_length=1, max_length=160)
    event_type: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0.0, le=1.0)
    site_id: int | None = None
    zone_id: str | None = Field(default=None, max_length=160)
    timestamp: datetime
    approx_location: GeoPoint | None = None
    evidence_clip_id: str | None = None
    signature: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class SensorEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_event_id: str
    sensor_id: str
    site_id: int
    zone_id: str | None = None
    event_type: str
    confidence: float
    timestamp: datetime
    approx_location: dict[str, Any] | None = None
    evidence_clip_id: str | None = None
    signature_valid: bool
    status: str
    rejection_reason: str | None = None
    created_at: datetime


class SensorEventResponse(BaseModel):
    event: SensorEventOut
    action: Literal["rejected", "duplicate", "notify_only", "approval_required", "dispatched"]
    mission_run: MissionRunOut | None = None
    incident_id: int | None = None
    validation: ValidationResult


class IncidentCreate(BaseModel):
    site_id: int
    mission_run_id: int | None = None
    sensor_event_id: int | None = None
    source: Literal["patrol", "sensor", "manual", "yolo"]
    event_type: str
    severity: str = "medium"
    confidence: float | None = None
    zone_id: str | None = None
    detected_objects: list[str] = Field(default_factory=list)
    start_time: datetime
    end_time: datetime | None = None
    location: GeoPoint | None = None
    video_clip_id: str | None = None
    snapshot_ids: list[str] = Field(default_factory=list)
    llm_summary: str | None = None
    operator_notes: str | None = None


class IncidentUpdate(BaseModel):
    status: IncidentStatus | None = None
    operator_notes: str | None = None
    llm_summary: str | None = None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    mission_run_id: int | None = None
    sensor_event_id: int | None = None
    source: str
    event_type: str
    severity: str
    confidence: float | None = None
    zone_id: str | None = None
    detected_objects: list[Any]
    start_time: datetime
    end_time: datetime | None = None
    location: dict[str, Any] | None = None
    video_clip_id: str | None = None
    snapshot_ids: list[Any]
    llm_summary: str | None = None
    operator_notes: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _flatten_location(cls, value: Any) -> Any:
        return value
