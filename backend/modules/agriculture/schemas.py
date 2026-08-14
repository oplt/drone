from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AgricultureAnalyticsConfiguration(BaseModel):
    expected_plant_spacing_m: float | None = Field(default=None, gt=0, le=10)
    stand_gap_multiplier: float = Field(default=1.75, gt=1, le=10)
    weed_density_cell_m: float = Field(default=10.0, ge=2, le=100)
    weed_hotspot_percentile: float = Field(default=0.8, gt=0, le=1)


class AgricultureMissionProfile(AgricultureAnalyticsConfiguration):
    flight_kind: Literal["agriculture_survey"] = "agriculture_survey"
    preset: Literal["early_stand_count", "rgb_weed_water", "repeat_monitoring", "multispectral_thermal"] = "rgb_weed_water"
    crop_type: str | None = Field(default=None, max_length=96)
    variety: str | None = Field(default=None, max_length=128)
    season: str | None = Field(default=None, max_length=64)
    growth_stage: str | None = Field(default=None, max_length=64)
    row_direction_deg: float | None = Field(default=None, ge=0, lt=360)
    expected_row_spacing_m: float | None = Field(default=None, gt=0, le=20)
    target_gsd_cm: float = Field(default=2.0, gt=0, le=100)
    speed_mps: float = Field(default=5.0, gt=0.1, le=20)
    front_overlap_pct: float = Field(default=70.0, ge=0, le=95)
    side_overlap_pct: float = Field(default=60.0, ge=0, le=95)
    camera_orientation: Literal["nadir", "oblique"] = "nadir"
    fov_h_deg: float = Field(default=78.0, gt=1, lt=179)
    fov_v_deg: float = Field(default=62.0, gt=1, lt=179)
    camera_resolution_width_px: int = Field(default=4000, ge=64, le=100_000)
    camera_resolution_height_px: int = Field(default=3000, ge=64, le=100_000)
    focal_length_mm: float | None = Field(default=None, gt=0, le=1000)
    grid_angle_deg: float | None = Field(default=None, ge=0, lt=180)
    sensor_inventory: list[Literal["rgb", "multispectral", "thermal", "stereo", "lidar"]] = Field(default_factory=lambda: ["rgb"])
    calibration_ids: list[str] = Field(default_factory=list)
    requested_analyses: list[str] = Field(default_factory=lambda: ["quality", "coverage"])
    repeat_interval_days: int | None = Field(default=None, ge=1, le=365)
    plan_id: str | None = Field(default=None, min_length=3, max_length=64)
    preflight_snapshot_id: str | None = Field(default=None, min_length=3, max_length=64)

    @field_validator("sensor_inventory")
    @classmethod
    def validate_sensors(cls, values: list[str]) -> list[str]:
        allowed = {"rgb", "multispectral", "thermal", "stereo", "lidar"}
        normalized = sorted({str(v).strip().lower() for v in values if str(v).strip()})
        if not normalized or not set(normalized).issubset(allowed):
            raise ValueError(f"sensor_inventory must use: {', '.join(sorted(allowed))}")
        return normalized


class FieldProfilePatch(AgricultureAnalyticsConfiguration):
    crop_type: str | None = Field(default=None, max_length=96)
    variety: str | None = Field(default=None, max_length=128)
    season: str | None = Field(default=None, max_length=64)
    planting_date: date | None = None
    growth_stage: str | None = Field(default=None, max_length=64)
    row_direction_deg: float | None = Field(default=None, ge=0, lt=360)
    expected_row_spacing_m: float | None = Field(default=None, gt=0, le=20)
    soil_type: str | None = Field(default=None, max_length=96)
    irrigation_method: str | None = Field(default=None, max_length=96)
    management_zone: str | None = Field(default=None, max_length=96)
    timezone: str = Field(default="UTC", max_length=64)
    notes: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanPreviewRequest(BaseModel):
    field_id: int | None = None
    field_polygon_lonlat: list[list[float]] = Field(..., min_length=3)
    cruise_alt_m: float = Field(default=30, gt=0, le=500)
    route_length_m: float | None = Field(default=None, ge=0)
    profile: AgricultureMissionProfile = Field(default_factory=AgricultureMissionProfile)


class PlanPreviewOut(BaseModel):
    field_id: int | None = None
    area_m2: float
    area_ha: float
    footprint_width_m: float
    footprint_height_m: float
    estimated_gsd_cm: float
    coverage_pct: float
    estimated_duration_s: float | None = None
    estimated_image_count: int | None = None
    warnings: list[str] = Field(default_factory=list)


class AgriculturePlanIn(BaseModel):
    field_id: int = Field(..., ge=1)
    field_polygon_lonlat: list[list[float]] = Field(..., min_length=3)
    cruise_alt_m: float = Field(default=30, gt=0, le=500)
    row_spacing_m: float = Field(default=7.5, gt=0, le=200)
    grid_angle_deg: float = Field(default=0, ge=0, lt=180)
    safety_inset_m: float = Field(default=1.5, ge=0, le=100)
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    crosshatch_angle_offset_deg: float = Field(default=90, gt=0, lt=180)
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    row_stride: int = Field(default=1, ge=1, le=20)
    row_phase_m: float = Field(default=0, ge=0, le=500)
    max_waypoints_per_segment: int = Field(default=500, ge=2, le=10_000)
    exclusion_zones: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    obstacle_zones: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    takeoff_point_lonlat: list[float] | None = Field(default=None, min_length=2, max_length=2)
    landing_point_lonlat: list[float] | None = Field(default=None, min_length=2, max_length=2)
    profile: AgricultureMissionProfile = Field(default_factory=AgricultureMissionProfile)


class AgriculturePlanOut(BaseModel):
    id: str
    field_id: int
    status: str
    plan_hash: str
    payload: dict[str, Any]
    route_geojson: dict[str, Any]
    estimates: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    created_at: datetime
    grid_revision: int = 1
    planner_version: str = "agriculture-grid.v1"


class AgricultureGridUpdateIn(BaseModel):
    expected_revision: int = Field(..., ge=1)
    route_lonlat: list[list[float]] = Field(..., min_length=2, max_length=100_000)


class AgriculturePreflightIn(BaseModel):
    checks: dict[str, bool | None] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)


class AgriculturePreflightAcknowledgeIn(BaseModel):
    operator_confirmed: bool = False


class AgriculturePreflightOut(BaseModel):
    id: str
    plan_id: str
    status: str
    checks: list[dict[str, Any]]
    acknowledged: bool
    expires_at: datetime
    evaluated_at: datetime | None = None
    evaluator_version: str = "agriculture-preflight.v2"
    signoff_hash: str | None = None
    operator_notes: str | None = None


class TelemetrySampleIn(BaseModel):
    timestamp: datetime
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    relative_altitude_m: float | None = None
    absolute_altitude_m: float | None = None
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None
    gimbal_roll_deg: float | None = None
    gimbal_pitch_deg: float | None = None
    gimbal_yaw_deg: float | None = None
    ground_speed_mps: float | None = None
    gps_quality: float | None = Field(default=None, ge=0, le=100)
    camera_trigger: bool | None = None
    source: str = Field(default="upload", max_length=64)
    source_key: str | None = Field(default=None, max_length=160)
    raw: dict[str, Any] = Field(default_factory=dict)


class TelemetryBatchIn(BaseModel):
    samples: list[TelemetrySampleIn] = Field(..., min_length=1, max_length=10000)
    clock_offset_seconds: float = Field(default=0.0, ge=-86_400, le=86_400)
    model_config = {"json_schema_extra": {"examples": [{"samples": [{"timestamp": "2026-08-03T10:00:00Z", "lat": 50.8503, "lon": 4.3517, "relative_altitude_m": 30, "camera_trigger": True}], "clock_offset_seconds": 0}]}}


class FlightManifestIn(BaseModel):
    kind: Literal["exif", "sidecar", "flight_manifest"]
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    checksum: str = Field(..., min_length=16, max_length=128)
    payload: dict[str, Any]
    model_config = {"json_schema_extra": {"examples": [{"kind": "flight_manifest", "idempotency_key": "manifest-flight-001", "checksum": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "payload": {"camera": "RGB-01", "timezone": "UTC"}}]}}


class MediaManifestIn(BaseModel):
    source_kind: Literal["rgb_video", "rgb_stills", "multispectral", "multispectral_band", "thermal", "orthomosaic"]
    storage_key: str = Field(..., min_length=1, max_length=1024)
    checksum: str = Field(..., min_length=16, max_length=128)
    content_type: str | None = None
    codec: str | None = Field(default=None, max_length=64)
    byte_size: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_seconds: float | None = Field(default=None, ge=0)
    camera_serial: str | None = None
    calibration_id: str | None = None
    capture_start: datetime | None = None
    capture_end: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = {"json_schema_extra": {"examples": [{"source_kind": "rgb_video", "storage_key": "org/7/flights/flight-1/capture.mp4", "checksum": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "content_type": "video/mp4", "codec": "h264"}]}}


class MediaLifecycleIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class ResumableUploadIn(BaseModel):
    source_kind: Literal["rgb_video", "rgb_stills", "multispectral", "multispectral_band", "thermal", "orthomosaic"]
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = None
    total_bytes: int = Field(..., gt=0)
    checksum: str = Field(..., min_length=16, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CalibrationIn(BaseModel):
    id: str = Field(..., min_length=3, max_length=128)
    camera_serial: str = Field(..., min_length=1, max_length=128)
    calibration_type: Literal["rgb", "multispectral", "thermal", "stereo", "lidar"] = "rgb"
    intrinsics: dict[str, Any] = Field(default_factory=dict)
    distortion: dict[str, Any] = Field(default_factory=dict)
    extrinsics: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime | None = None
    checksum: str = Field(..., min_length=16, max_length=128)


class FrameManifestItem(BaseModel):
    frame_index: int = Field(..., ge=0)
    timestamp: datetime
    image_width: int | None = Field(default=None, ge=1)
    image_height: int | None = Field(default=None, ge=1)
    pose_interpolation_status: Literal["unresolved", "exact", "interpolated", "extrapolated", "unavailable"] = "unresolved"
    telemetry_sample_before_id: int | None = Field(default=None, ge=1)
    telemetry_sample_after_id: int | None = Field(default=None, ge=1)
    footprint_geojson: dict[str, Any] = Field(default_factory=dict)
    gsd_cm: float | None = Field(default=None, gt=0)
    quality_metrics: dict[str, Any] = Field(default_factory=dict)
    evidence_artifact_ids: list[str] = Field(default_factory=list, max_length=1000)


class FrameManifestIn(BaseModel):
    media_id: str = Field(..., min_length=3, max_length=64)
    source_checksum: str = Field(..., min_length=16, max_length=128)
    telemetry_checksum: str | None = Field(default=None, min_length=16, max_length=128)
    sampling_config: dict[str, Any] = Field(default_factory=dict)
    frames: list[FrameManifestItem] = Field(..., min_length=1, max_length=100_000)


class AnalysisRunIn(BaseModel):
    requested_analyses: list[str] = Field(default_factory=lambda: ["quality", "coverage"])
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    model_versions: dict[str, str] = Field(default_factory=dict)
    calibration_versions: dict[str, str] = Field(default_factory=dict)
    analysis_profile: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    baseline_flight_id: str | None = Field(default=None, max_length=64)


class AgricultureCapabilityReadinessOut(BaseModel):
    id: str
    label: str
    description: str
    available: bool
    recommended: bool
    unavailable_reasons: list[str] = Field(default_factory=list)
    required_sensor: str
    required_media: str
    requires_model: bool
    output_type: str
    action_relevance: str
    crop_specific: bool = False
    capture_conditions: dict[str, Any] = Field(default_factory=dict)
    evaluation_thresholds: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    advanced_defaults: dict[str, Any] = Field(default_factory=dict)
    release: dict[str, Any] | None = None


class AgricultureAnalysisReadinessOut(BaseModel):
    catalog_version: str
    flight_id: str
    mission_id: str
    ready: bool
    media_count: int
    sensor_inventory: list[str]
    capture_prerequisites: list[dict[str, Any]]
    capabilities: list[AgricultureCapabilityReadinessOut]


class ReviewIn(BaseModel):
    status: Literal["confirmed", "rejected", "relabelled"]
    label: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2000)
    model_config = {"json_schema_extra": {"examples": [{"status": "confirmed", "label": "weed_cluster", "note": "Verified during field walk"}]}}


class ObservationAssignmentIn(BaseModel):
    assigned_to_user_id: int | None = Field(default=None, ge=1)
    review_due_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=2000)


class ObservationFeedbackIn(BaseModel):
    feedback_type: Literal["correction", "disagreement", "comment"] = "correction"
    proposed_label: str | None = Field(default=None, max_length=128)
    proposed_severity: float | None = Field(default=None, ge=0, le=1)
    proposed_zone_kind: Literal["observation", "management_zone", "prescription_zone"] | None = None
    proposed_geometry_geojson: dict[str, Any] = Field(default_factory=dict)
    comment: str = Field(..., min_length=1, max_length=4000)
    evidence_ids: list[Any] = Field(default_factory=list, max_length=500)


class ObservationFeedbackOut(ObservationFeedbackIn):
    id: str
    observation_id: str
    actor_user_id: int | None = None
    org_id: int | None = None
    status: Literal["submitted", "accepted", "rejected"]
    decision_note: str | None = None
    annotation_id: str | None = None
    decided_by_user_id: int | None = None
    decided_at: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class FeedbackDecisionIn(BaseModel):
    status: Literal["accepted", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


class ObservationAlertIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=4000)
    severity: Literal["info", "warning", "critical"] = "warning"
    due_at: datetime | None = None


class AnalysisProcessIn(BaseModel):
    force: bool = False
    cluster_radius_m: float = Field(default=8.0, gt=0.5, le=100)


class TemporalCompareIn(BaseModel):
    reference_flight_id: str | None = Field(default=None, min_length=1, max_length=64)
    min_quality_score: float = Field(default=0.6, ge=0, le=1)


class FieldComparisonIn(BaseModel):
    current_flight_id: str = Field(..., min_length=1, max_length=64)
    reference_flight_id: str | None = Field(default=None, min_length=1, max_length=64)
    min_quality_score: float = Field(default=0.6, ge=0, le=1)
    model_config = {"json_schema_extra": {"examples": [{"current_flight_id": "flight-current", "reference_flight_id": "flight-reference", "min_quality_score": 0.7}]}}


class AnnotationIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=128)
    severity: float = Field(default=0, ge=0, le=1)
    geometry_geojson: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[Any] = Field(default_factory=list, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    status: Literal["draft", "submitted", "approved", "rejected"] = "draft"


class AnnotationOut(AnnotationIn):
    id: str
    observation_id: str
    version: int
    created_by_user_id: int | None = None
    approved_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewAuditOut(BaseModel):
    id: str
    observation_id: str
    actor_user_id: int | None = None
    action: str
    from_state: str | None = None
    to_state: str | None = None
    reason: str | None = None
    annotation_version: int
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetExportIn(BaseModel):
    dataset_key: str = Field(..., min_length=1, max_length=128)
    annotation_ids: list[str] = Field(default_factory=list, max_length=50_000)
    split: Literal["train", "validation", "test", "shadow", "holdout"] = "train"


class DatasetImportIn(BaseModel):
    dataset_key: str = Field(..., min_length=1, max_length=128)
    items: list[dict[str, Any]] = Field(..., min_length=1, max_length=50_000)
    split: Literal["train", "validation", "test", "shadow", "holdout"] = "holdout"
    crop_types: list[str] = Field(default_factory=list, max_length=100)
    growth_stages: list[str] = Field(default_factory=list, max_length=100)
    sensor_type: Literal["rgb", "multispectral", "thermal", "stereo", "lidar"] = "rgb"
    holdout_field_count: int = Field(default=0, ge=0)
    holdout_flight_count: int = Field(default=0, ge=0)
    source_checksum: str | None = Field(default=None, min_length=16, max_length=128)


class DatasetExportOut(BaseModel):
    id: str
    dataset_key: str
    direction: str
    status: str
    manifest: dict[str, Any]
    checksum: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelVersionIn(BaseModel):
    task: str = Field(..., min_length=1, max_length=64)
    version: str = Field(..., min_length=1, max_length=160)
    status: Literal["candidate", "validated", "deployed", "retired"] = "candidate"
    artifact_uri: str | None = Field(default=None, max_length=2000)
    dataset_key: str | None = Field(default=None, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ModelQualityReportIn(BaseModel):
    scope: str = Field(default="all", max_length=64)
    metrics: dict[str, Any] = Field(default_factory=dict)
    slices: dict[str, Any] = Field(default_factory=dict)
    drift: dict[str, Any] = Field(default_factory=dict)


class SensorCalibrationIn(BaseModel):
    id: str = Field(..., min_length=3, max_length=128)
    sensor_serial: str = Field(..., min_length=1, max_length=128)
    sensor_type: Literal["multispectral", "thermal", "weather", "humidity", "soil_moisture", "irrigation"]
    version: str = Field(..., min_length=1, max_length=160)
    calibration_kind: str = Field(..., min_length=1, max_length=64)
    calibration_data: dict[str, Any] = Field(default_factory=dict)
    checksum: str = Field(..., min_length=16, max_length=128)
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class SpectralBandIn(BaseModel):
    media_id: str = Field(..., min_length=3, max_length=64)
    band_name: Literal["blue", "green", "red", "red_edge", "nir", "thermal"]
    wavelength_nm: float | None = Field(default=None, gt=0, le=3000)
    storage_key: str = Field(..., min_length=1, max_length=1024)
    checksum: str = Field(..., min_length=16, max_length=128)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    capture_timestamp: datetime | None = None
    sensor_serial: str | None = None
    calibration_id: str | None = None
    exposure_ms: float | None = Field(default=None, gt=0)
    irradiance: dict[str, Any] = Field(default_factory=dict)
    reflectance_panel: dict[str, Any] = Field(default_factory=dict)
    registration_transform: dict[str, Any] = Field(default_factory=dict)
    alignment_status: Literal["unvalidated", "pass", "failed"] = "unvalidated"
    quality_status: Literal["unvalidated", "pass", "warning", "failed"] = "unvalidated"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SensorReadingIn(BaseModel):
    sensor_type: Literal["weather", "humidity", "soil_moisture", "irrigation"]
    source: str = Field(..., min_length=1, max_length=128)
    sensor_serial: str | None = None
    timestamp_utc: datetime
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    scope_geojson: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    units: dict[str, Any] = Field(default_factory=dict)
    quality: float = Field(default=0, ge=0, le=1)
    stale_after_seconds: float | None = Field(default=900, gt=0, le=31_536_000)
    raw: dict[str, Any] = Field(default_factory=dict)


class SensorReadingBatchIn(BaseModel):
    readings: list[SensorReadingIn] = Field(..., min_length=1, max_length=100_000)


class FusionIn(BaseModel):
    requested_indices: list[Literal["ndvi", "gndvi", "ndre"]] = Field(default_factory=lambda: ["ndvi"])
    band_values: dict[str, list[float]] = Field(default_factory=dict)
    thermal_values_c: list[float] = Field(default_factory=list)
    thermal_calibrated: bool = False
    environmental_context: dict[str, float] = Field(default_factory=dict)
    geometries: list[dict[str, Any]] = Field(default_factory=list, max_length=100_000)
    visual_inputs: dict[str, float] = Field(default_factory=dict)
    crop_context: dict[str, Any] = Field(default_factory=dict)
    history: dict[str, float] = Field(default_factory=dict)


class FusionResultOut(BaseModel):
    layer: str
    status: str
    measured: bool
    units: str | None = None
    summary: dict[str, Any]
    required_inputs: list[Any]
    source_ids: list[Any]
    source_timestamps: list[Any]
    confidence: float
    uncertainty: dict[str, Any]
    evidence: list[Any]
    failure_reasons: list[Any]
    model_version: str | None = None

    model_config = {"from_attributes": True}


class CropRiskIn(BaseModel):
    visual_inputs: dict[str, Any] = Field(default_factory=dict)
    fusion_inputs: dict[str, Any] = Field(default_factory=dict)
    thermal_inputs: dict[str, Any] = Field(default_factory=dict)
    sensor_inputs: dict[str, Any] = Field(default_factory=dict)
    history: dict[str, Any] = Field(default_factory=dict)
    geometry_geojson: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[Any] = Field(default_factory=list, max_length=5000)
    model_version_id: str | None = Field(default=None, max_length=64)


class GrowthMetricIn(BaseModel):
    metric_kind: Literal["height", "biomass"]
    values: list[float] = Field(default_factory=list, max_length=100_000)
    units: str = Field(default="m", max_length=32)
    source_kind: Literal["stereo", "lidar", "photogrammetry", "unknown"] = "unknown"
    source_ids: list[Any] = Field(default_factory=list, max_length=5000)
    source_timestamps: list[Any] = Field(default_factory=list, max_length=5000)
    previous_mean: float | None = None
    evidence_ids: list[Any] = Field(default_factory=list, max_length=5000)
    calibration_valid: bool = False


class GrowthStageIn(BaseModel):
    features: dict[str, Any] = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list, max_length=100)
    evidence_ids: list[Any] = Field(default_factory=list, max_length=5000)


class GrowthStageCorrectionIn(BaseModel):
    human_stage: str = Field(..., min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class HarvestLabelIn(BaseModel):
    harvest_date: datetime
    crop_type: str = Field(..., min_length=1, max_length=96)
    variety: str | None = Field(default=None, max_length=128)
    yield_value: float = Field(..., ge=0)
    yield_unit: str = Field(..., min_length=1, max_length=32)
    area_ha: float | None = Field(default=None, gt=0)
    source: str = Field(..., min_length=1, max_length=128)
    quality: float = Field(default=0.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class YieldForecastIn(BaseModel):
    units: str | None = Field(default=None, max_length=32)
    feature_adjustment: float = Field(default=0.0, ge=-1, le=1)
    evidence_ids: list[Any] = Field(default_factory=list, max_length=5000)


class CropRiskOut(BaseModel):
    id: str
    run_id: str
    flight_id: str
    field_id: int
    issue_type: str
    status: str
    crop_type: str | None = None
    growth_stage: str | None = None
    geometry_geojson: dict[str, Any]
    severity: float
    confidence: float
    trend: str
    uncertainty: dict[str, Any]
    evidence_ids: list[Any]
    sensor_values: dict[str, Any]
    inspection_points: list[Any]
    factors: dict[str, Any]
    applicability: dict[str, Any]
    model_version: str | None = None
    review_state: str
    review_note: str | None = None
    reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}


class GrowthMetricOut(BaseModel):
    id: str
    run_id: str
    flight_id: str
    field_id: int
    metric_kind: str
    status: str
    units: str | None = None
    summary: dict[str, Any]
    source_ids: list[Any]
    source_timestamps: list[Any]
    confidence: float
    uncertainty: dict[str, Any]
    evidence_ids: list[Any]
    model_version: str | None = None

    model_config = {"from_attributes": True}


class GrowthStageOut(BaseModel):
    id: str
    run_id: str
    flight_id: str
    field_id: int
    status: str
    predicted_stage: str | None = None
    candidates: list[Any]
    confidence: float
    inputs: dict[str, Any]
    evidence_ids: list[Any]
    uncertainty: dict[str, Any]
    human_stage: str | None = None
    correction_note: str | None = None
    corrected_at: datetime | None = None
    model_version: str | None = None

    model_config = {"from_attributes": True}


class HarvestLabelOut(BaseModel):
    id: str
    field_id: int
    harvest_date: datetime
    crop_type: str
    variety: str | None = None
    yield_value: float
    yield_unit: str
    area_ha: float | None = None
    source: str
    quality: float
    metadata: dict[str, Any]

    model_config = {"from_attributes": True}


class YieldForecastOut(BaseModel):
    id: str
    run_id: str
    flight_id: str
    field_id: int
    status: str
    units: str | None = None
    forecast_range: dict[str, Any]
    confidence_interval: dict[str, Any]
    confidence: float
    factors: dict[str, Any]
    applicability: dict[str, Any]
    evidence_ids: list[Any]
    harvest_label_ids: list[Any]
    uncertainty: dict[str, Any]
    model_version: str | None = None

    model_config = {"from_attributes": True}


class InspectionPlanIn(BaseModel):
    no_go_geometries: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    max_actions: int = Field(default=50, ge=1, le=500)
    battery_budget_s: float | None = Field(default=None, gt=0)
    seconds_per_action: float = Field(default=90, gt=10, le=3600)


class InspectionActionOut(BaseModel):
    id: str
    run_id: str
    flight_id: str
    field_id: int
    source_ids: list[Any]
    priority_rank: int
    priority_score: float
    severity: float
    confidence: float
    area_m2: float | None = None
    issue_type: str
    geometry_geojson: dict[str, Any]
    waypoint_geojson: dict[str, Any]
    rationale: str
    route_constraints: dict[str, Any]
    uncertainty: dict[str, Any]
    status: str
    review_note: str | None = None
    assigned_to_user_id: int | None = None
    due_at: datetime | None = None
    reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}


class InspectionActionAssignmentIn(BaseModel):
    assigned_to_user_id: int | None = Field(default=None, ge=1)
    due_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=2000)


class InspectionPlanOut(BaseModel):
    status: str
    actions: list[InspectionActionOut]
    rejected: list[dict[str, Any]]
    constraints: dict[str, Any]
    source_count: int


class ApprovalIn(BaseModel):
    status: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


class AgricultureAssistantIn(BaseModel):
    task: Literal["summary", "comparison", "inspection_checklist", "field_question"] = "summary"
    question: str = Field(default="Summarize the validated agriculture evidence.", min_length=1, max_length=4000)


class AgricultureAssistantOut(BaseModel):
    id: str
    run_id: str
    field_id: int
    flight_id: str
    task: str
    status: str
    decision_status: str
    prompt_version: str
    context_checksum: str
    source_ids: list[Any]
    deterministic_rules: list[Any]
    output: dict[str, Any]
    citations: list[Any]
    limitations: list[Any]
    confidence: float
    risk_level: str
    requires_human_approval: bool
    abstained: bool
    profile_id: str | None = None
    model: str | None = None
    error_code: str | None = None
    review_status: str
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgronomyRuleIn(BaseModel):
    rule_key: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., min_length=1, max_length=64)
    jurisdiction: str = Field(..., min_length=1, max_length=128)
    crop_type: str | None = Field(default=None, max_length=96)
    issue_type: str = Field(..., min_length=1, max_length=96)
    action_kind: Literal["inspection_only", "fertilizer", "chemical"] = "inspection_only"
    parameters: dict[str, Any] = Field(default_factory=dict)
    regulatory_reference: str | None = Field(default=None, max_length=2000)
    status: Literal["draft", "approved", "retired"] = "draft"


class AgronomyRuleOut(AgronomyRuleIn):
    id: str
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PrescriptionIn(BaseModel):
    rule_id: str | None = Field(default=None, max_length=64)
    minimum_confidence: float = Field(default=0.6, ge=0, le=1)


class PrescriptionOut(BaseModel):
    id: str
    run_id: str
    flight_id: str
    field_id: int
    rule_id: str | None = None
    status: str
    zones: list[Any]
    source_ids: list[Any]
    rule_provenance: dict[str, Any]
    model_provenance: dict[str, Any]
    assumptions: list[Any]
    confidence: float
    uncertainty: dict[str, Any]
    review_note: str | None = None
    reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExportIn(BaseModel):
    artifact_kind: Literal["observations", "report", "inspection_actions", "prescription", "intervention_zones"]
    format: Literal["geojson", "shapefile", "csv", "pdf"]
    source_id: str | None = Field(default=None, max_length=64)
    model_config = {"json_schema_extra": {"examples": [{"artifact_kind": "observations", "format": "geojson"}, {"artifact_kind": "report", "format": "pdf"}]}}


class ExportOut(BaseModel):
    id: str
    field_id: int
    flight_id: str | None = None
    run_id: str | None = None
    artifact_kind: str
    format: str
    status: str
    checksum: str | None = None
    content_type: str | None = None
    source_manifest: dict[str, Any]
    expires_at: datetime | None = None
    requested_by_user_id: int | None = None
    approved_by_user_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportSnapshotIn(BaseModel):
    template_key: Literal["standard", "executive", "field_visit", "decision"] = "standard"
    comparison_id: str | None = Field(default=None, min_length=1, max_length=64)


class ReportSnapshotOut(BaseModel):
    id: str
    field_id: int
    flight_id: str
    run_id: str
    template_key: str
    template_version: str
    snapshot_json: dict[str, Any]
    checksum: str
    created_by_user_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalysisStageOut(BaseModel):
    id: str
    run_id: str
    stage_name: str
    status: str
    attempt: int
    progress: float
    input_checksum: str | None = None
    output_checksum: str | None = None
    execution_key: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    task_id: str | None = None
    queue_name: str | None = None
    retryable: bool = True
    dead_letter: bool = False
    last_error_at: datetime | None = None
    dead_letter_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgricultureObservationOut(BaseModel):
    id: str
    run_id: str
    flight_id: str
    field_id: int
    observation_type: str
    zone_kind: str
    geometry_geojson: dict[str, Any]
    georef_status: str
    area_m2: float | None = None
    severity: float
    confidence: float
    uncertainty: dict[str, Any]
    provenance: dict[str, Any]
    first_detected: datetime | None = None
    last_detected: datetime | None = None
    trend: str
    evidence_ids: list[Any]
    sensor_values: dict[str, Any]
    model_version: str | None = None
    review_state: str
    review_label: str | None = None
    review_note: str | None = None
    assigned_to_user_id: int | None = None
    review_due_at: datetime | None = None
    reviewed_at: datetime | None = None
    merged_into_id: str | None = None
    split_from_id: str | None = None
    member_observation_ids: list[Any] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AgricultureObservationPage(BaseModel):
    schema_version: Literal["agriculture.v1"]
    items: list[AgricultureObservationOut]
    next_cursor: str | None
    total: int = Field(ge=0)


class AgricultureQualityOut(BaseModel):
    run_id: str
    status: str
    score: float
    summary: dict[str, Any] = Field(default_factory=dict)
    stages: list[AnalysisStageOut] = Field(default_factory=list)


class AnalysisStageRetryIn(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    reason: str | None = Field(default=None, max_length=500)


class AgricultureLayerOut(BaseModel):
    run_id: str
    layer: str
    status: str
    geojson: dict[str, Any]
    summary: dict[str, Any]
    checksum: str


class AgricultureFieldProfileOut(AgricultureAnalyticsConfiguration):
    id: int
    field_id: int
    crop_type: str | None = None
    variety: str | None = None
    season: str | None = None
    planting_date: str | None = None
    growth_stage: str | None = None
    row_direction_deg: float | None = None
    expected_row_spacing_m: float | None = None
    soil_type: str | None = None
    irrigation_method: str | None = None
    management_zone: str | None = None
    timezone: str
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class AgricultureFlightOut(BaseModel):
    id: str
    mission_id: str
    field_id: int
    org_id: int | None = None
    season: str | None = None
    flight_kind: str = "agriculture_survey"
    status: str
    profile_snapshot: dict[str, Any]
    profile_snapshot_version: int = 1
    profile_snapshot_hash: str | None = None
    quality_summary: dict[str, Any]
    coverage_summary: dict[str, Any]
    input_manifest: dict[str, Any]
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None

    class Config:
        from_attributes = True


class LiveAdvisoryOut(BaseModel):
    frame_index: int
    timestamp_seconds: float
    state: str
    alerts: list[str]
    geolocation: dict[str, float] | None = None
    expires_at: float
    sampler_hz: float
    dropped_frames: int
    source_of_truth: Literal["provisional_live"] = Field(
        default="provisional_live",
        description=(
            "Heuristic live RGB advisory only. Post-flight analysis runs remain "
            "the authoritative source for operator decisions."
        ),
    )


class AgricultureTelemetryOut(BaseModel):
    inserted: int
    duplicates: int
    rejected: int
    normalized_to_utc: bool = True
    gap_count: int


class InferenceReuseDetailOut(BaseModel):
    capability_id: str
    video_id: str
    video_job_id: str
    reused: bool
    reused_from_run_id: str | None = None
    source_checksum: str | None = None
    model_checksum: str | None = None
    vision_model_version_id: str | None = None
    inference_profile: dict[str, Any] = Field(default_factory=dict)
    original_completed_at: datetime | None = None


class InferenceReuseSummaryOut(BaseModel):
    run_input_checksum: str | None = None
    reused_job_count: int
    total_job_count: int
    fully_reused: bool
    details: list[InferenceReuseDetailOut] = Field(default_factory=list)


class AnalysisRunOut(BaseModel):
    id: str
    flight_id: str
    status: str
    requested_analyses: list[Any]
    analysis_profile: dict[str, Any]
    input_manifest: dict[str, Any]
    input_checksum: str | None = None
    model_versions: dict[str, Any]
    calibration_versions: dict[str, Any]
    parameters: dict[str, Any]
    baseline_flight_id: str | None = None
    retry_count: int
    audit_json: dict[str, Any]
    requested_by_user_id: int | None = None
    progress: float
    quality_gate: dict[str, Any]
    counters: dict[str, Any]
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    inference_reuse: InferenceReuseSummaryOut | None = None

    class Config:
        from_attributes = True


class FindingRankExplanationOut(BaseModel):
    policy_version: str
    score: float
    display_status: Literal["shown", "labeled_low_confidence", "withheld"]
    factors: dict[str, Any] = Field(default_factory=dict)
    withhold_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RankedFindingOut(BaseModel):
    rank: int
    finding_id: str
    observation_id: str
    observation_type: str | None = None
    geometry_geojson: dict[str, Any] = Field(default_factory=dict)
    severity: float
    confidence: float
    area_m2: float | None = None
    georef_status: str | None = None
    review_state: str | None = None
    evidence_ids: list[Any] = Field(default_factory=list)
    model_version: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    assigned_to_user_id: int | None = None
    merged_into_id: str | None = None
    member_observation_ids: list[Any] = Field(default_factory=list)
    score: float
    display_status: Literal["shown", "labeled_low_confidence", "withheld"]
    policy_version: str
    factors: dict[str, Any] = Field(default_factory=dict)
    withhold_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RankedFindingPage(BaseModel):
    schema_version: Literal["agriculture.v1"] = "agriculture.v1"
    policy_version: str
    run_id: str
    limit: int
    total_candidates: int
    items: list[RankedFindingOut]
    hotspots: dict[str, Any]


class FindingMergeIn(BaseModel):
    primary_observation_id: str = Field(..., min_length=1, max_length=64)
    member_observation_ids: list[str] = Field(..., min_length=1, max_length=50)
    reason: str | None = Field(default=None, max_length=2000)


class FindingSplitPartIn(BaseModel):
    geometry_geojson: dict[str, Any]
    observation_type: str | None = Field(default=None, max_length=64)
    severity: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    area_m2: float | None = Field(default=None, ge=0)
    evidence_ids: list[Any] = Field(default_factory=list, max_length=500)


class FindingSplitIn(BaseModel):
    parts: list[FindingSplitPartIn] = Field(..., min_length=2, max_length=20)
    reason: str | None = Field(default=None, max_length=2000)


class FieldOutcomeIn(BaseModel):
    observation_id: str = Field(..., min_length=1, max_length=64)
    outcome_status: Literal[
        "confirmed_present",
        "false_positive",
        "treated",
        "unresolved",
        "other",
    ]
    notes: str | None = Field(default=None, max_length=4000)
    model_version: str | None = Field(default=None, max_length=160)
    capability_release_id: str | None = Field(default=None, max_length=64)


class FieldOutcomeOut(BaseModel):
    id: str
    org_id: int | None = None
    field_id: int
    flight_id: str
    run_id: str
    observation_id: str
    outcome_status: str
    notes: str | None = None
    model_version: str | None = None
    capability_release_id: str | None = None
    created_by_user_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InspectionRouteUpdateIn(BaseModel):
    ordered_action_ids: list[str] = Field(default_factory=list, max_length=500)
    removed_action_ids: list[str] = Field(default_factory=list, max_length=500)
    reason: str | None = Field(default=None, max_length=2000)


class ComparableFlightOut(BaseModel):
    flight_id: str
    created_at: str | None = None
    status: str | None = None
    comparability: dict[str, Any] = Field(default_factory=dict)
    alignment: dict[str, Any] = Field(default_factory=dict)
