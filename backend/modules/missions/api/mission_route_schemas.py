from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.modules.missions.schemas.mission_create import (
    MissionCreateIn,
    MissionCreateOut,
    PatrolTaskType,
    validate_private_patrol_task_inputs,
)
from backend.modules.patrol.planning import PATROL_AI_TASKS
from backend.modules.preflight.checks.schemas import PreflightReport

__all__ = [
    "FlightEventOut",
    "MissionCreateIn",
    "MissionCreateOut",
    "MissionPreflightOut",
    "MissionRuntimeOut",
    "PreflightRunOut",
    "PrivatePatrolPreviewIn",
    "PrivatePatrolPreviewOut",
    "PrivatePatrolTaskCatalogOut",
    "PrivatePatrolTaskTemplateOut",
    "ResumableMissionOut",
    "StateTransitionOut",
]


class MissionRuntimeOut(BaseModel):
    flight_id: str
    mission_name: str
    mission_type: str
    mission_task_type: str | None = None
    state: str
    created_at: float
    updated_at: float
    preflight_run_id: str | None = None
    db_flight_id: str | None = None
    last_error: str | None = None


class StateTransitionOut(BaseModel):
    state: str
    entered_at: float
    trigger: str
    command_id: str | None = None
    command: str | None = None
    reason: str | None = None


class ResumableMissionOut(BaseModel):
    flight_id: str
    mission_name: str
    mission_type: str
    mission_task_type: str | None = None
    state: str
    ended_at: float | None = None
    failure_reason: str | None = None
    resume_metadata: dict
    mission_params: dict


class PreflightRunOut(BaseModel):
    preflight_run_id: str
    mission_fingerprint: str
    overall_status: str
    can_start_mission: bool
    created_at: float
    expires_at: float
    report: PreflightReport


class MissionPreflightOut(BaseModel):
    preflight_run_id: str
    overall_status: str
    base_checks: list[dict]
    mission_checks: list[dict]
    critical_failures: list[str]
    summary: dict
    started_at: float | None = None
    completed_at: float | None = None


class FlightEventOut(BaseModel):
    id: int
    type: str
    data: dict
    created_at: float


class PrivatePatrolTaskTemplateOut(BaseModel):
    id: str
    label: str
    purpose: str
    description: str
    default_params: dict
    ai_tasks: list[str]


class PrivatePatrolTaskCatalogOut(BaseModel):
    mission_category: str
    tasks: list[PrivatePatrolTaskTemplateOut]


class PrivatePatrolPreviewIn(BaseModel):
    task_type: Literal[
        "perimeter_patrol",
        "waypoint_patrol",
        "grid_surveillance",
        "event_triggered_patrol",
    ] = "perimeter_patrol"
    property_polygon_lonlat: list[list[float]] | None = Field(default=None, min_length=3)
    key_points_lonlat: list[list[float]] | None = Field(default=None, min_length=2)
    cruise_alt: float = Field(default=30.0, gt=0, le=500.0)
    path_offset_m: float = Field(default=15.0, ge=0.0, le=120.0)
    direction: Literal["clockwise", "counterclockwise"] = "clockwise"
    patrol_loops: int = Field(default=1, ge=1, le=200)
    speed_mps: float = Field(default=6.0, ge=0.5, le=20.0)
    start_after_minutes: int = Field(default=0, ge=0, le=1440)
    repeat_interval_minutes: int = Field(default=0, ge=0, le=1440)
    camera_angle_deg: float = Field(default=35.0, ge=0.0, le=90.0)
    camera_overlap_pct: float = Field(default=50.0, ge=0.0, le=95.0)
    max_segment_length_m: float = Field(default=20.0, gt=1.0, le=300.0)
    hover_time_s: float = Field(default=15.0, ge=1.0, le=300.0)
    camera_scan_yaw_deg: float = Field(default=360.0, ge=0.0, le=360.0)
    zoom_capture: bool = True
    return_to_start: bool = True
    grid_spacing_m: float = Field(default=40.0, gt=1.0, le=300.0)
    grid_angle_deg: float = Field(default=0.0, ge=0.0, lt=180.0)
    safety_inset_m: float = Field(default=2.0, ge=0.0, le=100.0)
    grid_pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    grid_crosshatch_angle_offset_deg: float = Field(default=90.0, gt=0.0, lt=180.0)
    grid_lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    grid_start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    grid_row_stride: int = Field(default=1, ge=1, le=20)
    grid_row_phase_m: float = Field(default=0.0, ge=0.0, le=500.0)
    trigger_event_location_lonlat: list[float] | None = Field(
        default=None, min_length=2, max_length=2
    )
    target_label: str | None = Field(default=None, max_length=120)
    verification_loiter_s: float = Field(default=45.0, ge=0.0, le=600.0)
    verification_radius_m: float = Field(default=18.0, ge=0.0, le=150.0)
    track_target: bool = True
    auto_stream_video: bool = True
    record_video_stream: bool = True
    ai_tasks: list[PatrolTaskType] = Field(default_factory=lambda: list(PATROL_AI_TASKS))

    @model_validator(mode="after")
    def _validate_by_task(self) -> PrivatePatrolPreviewIn:
        validate_private_patrol_task_inputs(
            task_type=self.task_type,
            property_polygon_lonlat=self.property_polygon_lonlat,
            key_points_lonlat=self.key_points_lonlat,
        )
        return self


class PrivatePatrolPreviewOut(BaseModel):
    waypoints: list[dict]
    work_leg_mask: list[bool]
    stats: dict
    camera: dict
    ai_tasks: list[str]
