from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS

PatrolSensorType = Literal[
    "generic_webhook",
    "camera",
    "motion",
    "fence",
    "access_control",
]
PatrolConnectorType = Literal["webhook", "mqtt", "onvif"]
PatrolAiTaskType = Literal[
    "intruder_detection",
    "vehicle_detection",
    "fence_breach_detection",
    "motion_detection",
]
PatrolResponseMode = Literal["incident_response", "detection_search"]


class PatrolSiteIn(BaseModel):
    field_id: int = Field(..., ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    enabled: bool = True


class PatrolSiteUpdate(BaseModel):
    field_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    enabled: bool | None = None


class PatrolSiteOut(BaseModel):
    id: int
    field_id: int
    field_name: str | None = None
    name: str
    description: str | None = None
    enabled: bool


class PatrolResponseProfileIn(BaseModel):
    site_id: int
    name: str = Field(..., min_length=1, max_length=160)
    cruise_alt: float = Field(default=30.0, ge=1.0, le=500.0)
    speed_mps: float = Field(default=6.0, ge=0.5, le=20.0)
    verification_loiter_s: float = Field(default=45.0, ge=0.0, le=600.0)
    verification_radius_m: float = Field(default=18.0, ge=0.0, le=150.0)
    track_target: bool = True
    target_label: str | None = Field(default=None, max_length=120)
    search_grid_spacing_m: float = Field(default=40.0, gt=1.0, le=300.0)
    search_grid_angle_deg: float = Field(default=0.0, ge=0.0, lt=180.0)
    ai_tasks: list[PatrolAiTaskType] = Field(default_factory=lambda: list(PATROL_AI_TASKS))
    is_default: bool = False
    enabled: bool = True


class PatrolResponseProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    cruise_alt: float | None = Field(default=None, ge=1.0, le=500.0)
    speed_mps: float | None = Field(default=None, ge=0.5, le=20.0)
    verification_loiter_s: float | None = Field(default=None, ge=0.0, le=600.0)
    verification_radius_m: float | None = Field(default=None, ge=0.0, le=150.0)
    track_target: bool | None = None
    target_label: str | None = Field(default=None, max_length=120)
    search_grid_spacing_m: float | None = Field(default=None, gt=1.0, le=300.0)
    search_grid_angle_deg: float | None = Field(default=None, ge=0.0, lt=180.0)
    ai_tasks: list[PatrolAiTaskType] | None = None
    is_default: bool | None = None
    enabled: bool | None = None


class PatrolResponseProfileOut(BaseModel):
    id: int
    site_id: int
    name: str
    cruise_alt: float
    speed_mps: float
    verification_loiter_s: float
    verification_radius_m: float
    track_target: bool
    target_label: str | None = None
    search_grid_spacing_m: float
    search_grid_angle_deg: float
    ai_tasks: list[str]
    is_default: bool
    enabled: bool

    model_config = {"from_attributes": True}


class PatrolSensorIn(BaseModel):
    site_id: int
    response_profile_id: int | None = None
    external_sensor_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=160)
    sensor_type: PatrolSensorType = "generic_webhook"
    location_lonlat: list[float] | None = Field(default=None, min_length=2, max_length=2)
    connector_type: PatrolConnectorType = "webhook"
    connector_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PatrolSensorUpdate(BaseModel):
    site_id: int | None = None
    response_profile_id: int | None = None
    external_sensor_id: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    sensor_type: PatrolSensorType | None = None
    location_lonlat: list[float] | None = Field(default=None, min_length=2, max_length=2)
    connector_type: PatrolConnectorType | None = None
    connector_config: dict[str, Any] | None = None
    enabled: bool | None = None


class PatrolMqttIntegrationOut(BaseModel):
    broker: str
    port: int
    use_tls: bool
    topic: str
    subscribe_pattern: str
    auth_hint: str
    qos: int = 1


class PatrolSensorIntegrationOut(BaseModel):
    webhook_url: str
    auth_hint: str
    example_body: dict[str, Any]
    mqtt: PatrolMqttIntegrationOut | None = None


class PatrolSensorOut(BaseModel):
    id: int
    site_id: int
    response_profile_id: int | None = None
    external_sensor_id: str
    name: str
    sensor_type: str
    location_lonlat: list[float] | None = None
    connector_type: str
    connector_config: dict[str, Any]
    enabled: bool
    integration: PatrolSensorIntegrationOut

    model_config = {"from_attributes": True}


class SensorLocationIn(BaseModel):
    sensor_id: str = Field(..., min_length=1, max_length=128)
    location_lonlat: list[float] = Field(..., min_length=2, max_length=2)


class PatrolSensorTriggerIn(BaseModel):
    """Inbound sensor trigger. Uses Property Patrol event-trigger setup when configured."""

    trigger_id: str = Field(..., min_length=1, max_length=128)
    sensor_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Optional source identifier for logs (any string from your sensor system).",
    )
    field_id: int | None = Field(
        default=None,
        ge=1,
        description="Optional property geofence; defaults to the active setup on Property Patrol.",
    )
    coordinates: list[float] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Optional trigger location as [lon, lat]",
    )
    mission_name: str | None = Field(default=None, max_length=120)
    # Legacy/manual overrides when sensor is not registered in DB
    geofence_polygon_lonlat: list[list[float]] | None = Field(default=None, min_length=3)
    sensor_registry: list[SensorLocationIn] | None = None
    cruise_alt: float | None = Field(default=None, ge=1.0, le=500.0)
    speed_mps: float | None = Field(default=None, ge=0.5, le=20.0)
    verification_loiter_s: float | None = Field(default=None, ge=0.0, le=600.0)
    verification_radius_m: float | None = Field(default=None, ge=0.0, le=150.0)
    track_target: bool | None = None
    search_grid_spacing_m: float | None = Field(default=None, gt=1.0, le=300.0)
    search_grid_angle_deg: float | None = Field(default=None, ge=0.0, lt=180.0)
    target_label: str | None = Field(default=None, max_length=120)
    ai_tasks: list[PatrolAiTaskType] | None = None

    @model_validator(mode="after")
    def _validate_coordinates(self) -> PatrolSensorTriggerIn:
        if self.coordinates is not None:
            lon, lat = float(self.coordinates[0]), float(self.coordinates[1])
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                raise ValueError("coordinates must be valid [lon, lat]")
        return self


class PatrolSensorTriggerOut(BaseModel):
    accepted: bool
    trigger_id: str
    response_mode: PatrolResponseMode
    resolved_location_lonlat: list[float] | None = None
    client_flight_id: str | None = None
    message: str
    duplicate: bool = False
    sensor_name: str | None = None
    site_name: str | None = None
    field_name: str | None = None


class PatrolEventTriggerConfigIn(BaseModel):
    field_id: int = Field(..., ge=1)
    enabled: bool = True
    cruise_alt: float = Field(default=30.0, ge=1.0, le=500.0)
    speed_mps: float = Field(default=6.0, ge=0.5, le=20.0)
    verification_loiter_s: float = Field(default=45.0, ge=0.0, le=600.0)
    verification_radius_m: float = Field(default=18.0, ge=0.0, le=150.0)
    track_target: bool = True
    target_label: str | None = Field(default=None, max_length=120)
    search_grid_spacing_m: float = Field(default=40.0, gt=1.0, le=300.0)
    search_grid_angle_deg: float = Field(default=0.0, ge=0.0, lt=180.0)
    ai_tasks: list[PatrolAiTaskType] = Field(default_factory=lambda: list(PATROL_AI_TASKS))


class PatrolEventTriggerConfigOut(BaseModel):
    id: int | None = None
    field_id: int
    field_name: str | None = None
    is_active: bool = False
    enabled: bool = True
    cruise_alt: float
    speed_mps: float
    verification_loiter_s: float
    verification_radius_m: float
    track_target: bool
    target_label: str | None = None
    search_grid_spacing_m: float
    search_grid_angle_deg: float
    ai_tasks: list[str]
    integration: PatrolSensorIntegrationOut | None = None
