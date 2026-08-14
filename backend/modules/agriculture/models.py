from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import event, inspect
from geoalchemy2 import Geometry

from backend.core.database.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


class AgricultureFieldProfile(Base):
    __tablename__ = "agriculture_field_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), unique=True, index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    crop_type: Mapped[str | None] = mapped_column(String(96))
    variety: Mapped[str | None] = mapped_column(String(128))
    season: Mapped[str | None] = mapped_column(String(64), index=True)
    planting_date: Mapped[str | None] = mapped_column(String(32))
    growth_stage: Mapped[str | None] = mapped_column(String(64))
    row_direction_deg: Mapped[float | None] = mapped_column(Float)
    expected_row_spacing_m: Mapped[float | None] = mapped_column(Float)
    soil_type: Mapped[str | None] = mapped_column(String(96))
    irrigation_method: Mapped[str | None] = mapped_column(String(96))
    management_zone: Mapped[str | None] = mapped_column(String(96))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AgricultureCameraCalibration(Base):
    """Versioned camera/gimbal calibration referenced by captured media."""

    __tablename__ = "agriculture_camera_calibrations"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    camera_serial: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    calibration_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rgb")
    intrinsics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    distortion_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    extrinsics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureFlight(Base):
    __tablename__ = "agriculture_flights"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    mission_id: Mapped[str] = mapped_column(ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"), unique=True, index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    season: Mapped[str | None] = mapped_column(String(64), index=True)
    flight_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="agriculture_survey", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    profile_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    profile_snapshot_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    quality_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    coverage_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    input_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_agri_flights_field_status", "field_id", "status"),
        Index("idx_agri_flights_org_created", "org_id", "created_at"),
        Index("idx_agri_flights_field_created", "field_id", "created_at"),
        CheckConstraint("flight_kind = 'agriculture_survey'", name="ck_agri_flight_kind"),
        CheckConstraint("status IN ('planned', 'preflight', 'running', 'captured', 'processing', 'review', 'published', 'archived', 'failed', 'cancelled')", name="ck_agri_flight_status"),
    )


@event.listens_for(AgricultureFlight, "before_update")
def _protect_flight_snapshot(mapper, connection, target: AgricultureFlight) -> None:
    state = inspect(target)
    if state.attrs.profile_snapshot.history.has_changes():
        raise ValueError("Agriculture flight profile snapshots are immutable")
    if state.attrs.input_manifest.history.has_changes():
        status_history = state.attrs.status.history
        previous_status = status_history.deleted[0] if status_history.deleted else target.status
        if previous_status in {"processing", "review", "published", "archived"}:
            raise ValueError("Agriculture flight input manifests are immutable after processing starts")


class AgricultureTelemetrySample(Base):
    __tablename__ = "agriculture_telemetry_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    relative_altitude_m: Mapped[float | None] = mapped_column(Float)
    absolute_altitude_m: Mapped[float | None] = mapped_column(Float)
    roll_deg: Mapped[float | None] = mapped_column(Float)
    pitch_deg: Mapped[float | None] = mapped_column(Float)
    yaw_deg: Mapped[float | None] = mapped_column(Float)
    gimbal_roll_deg: Mapped[float | None] = mapped_column(Float)
    gimbal_pitch_deg: Mapped[float | None] = mapped_column(Float)
    gimbal_yaw_deg: Mapped[float | None] = mapped_column(Float)
    ground_speed_mps: Mapped[float | None] = mapped_column(Float)
    gps_quality: Mapped[float | None] = mapped_column(Float)
    camera_trigger: Mapped[bool | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="runtime")
    source_key: Mapped[str | None] = mapped_column(String(160))
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("flight_id", "timestamp_utc", "source", name="uq_agri_telem_flight_time_source"),
        Index("idx_agri_telem_flight_time", "flight_id", "timestamp_utc"),
    )


class AgricultureTelemetryReceipt(Base):
    """Durable telemetry batch idempotency receipts (replaces JSON manifest map)."""

    __tablename__ = "agriculture_telemetry_receipts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    flight_id: Mapped[str] = mapped_column(
        ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "flight_id",
            "idempotency_key",
            name="uq_agri_telemetry_receipt_flight_key",
        ),
    )


class AgricultureRuntimeEvent(Base):
    """Durable, ordered agriculture runtime stream used by reconnecting clients."""

    __tablename__ = "agriculture_runtime_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    state: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str] = mapped_column(String(96), nullable=False, default="agriculture.runtime")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("flight_id", "sequence", name="uq_agri_runtime_event_sequence"),
        Index("idx_agri_runtime_event_flight_sequence", "flight_id", "sequence"),
    )


class AgricultureMediaManifest(Base):
    __tablename__ = "agriculture_media_manifests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128))
    codec: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    camera_serial: Mapped[str | None] = mapped_column(String(128))
    calibration_id: Mapped[str | None] = mapped_column(
        ForeignKey("agriculture_camera_calibrations.id", ondelete="SET NULL"), index=True
    )
    capture_start_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capture_end_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    security_status: Mapped[str] = mapped_column(String(24), nullable=False, default="passed", index=True)
    security_reason: Mapped[str | None] = mapped_column(String(512))
    security_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    storage_class: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
    artifact_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retention_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("flight_id", "checksum", "source_kind", name="uq_agri_media_flight_checksum_kind"),
        CheckConstraint("source_kind IN ('rgb_video', 'rgb_stills', 'multispectral', 'multispectral_band', 'thermal', 'orthomosaic')", name="ck_agri_media_source_kind"),
        CheckConstraint("retention_status IN ('active', 'archived', 'expired', 'legal_hold', 'deleted')", name="ck_agri_media_retention"),
        CheckConstraint("security_status IN ('pending', 'passed', 'quarantined', 'rejected')", name="ck_agri_media_security"),
        Index("idx_agri_media_flight_capture", "flight_id", "capture_start_utc"),
    )


class AgricultureUploadSession(Base):
    """Durable resumable-upload state; media is published only after checksum validation."""

    __tablename__ = "agriculture_upload_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    temporary_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128))
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    received_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="uploading", index=True)
    media_id: Mapped[str | None] = mapped_column(
        ForeignKey("agriculture_media_manifests.id", ondelete="SET NULL"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_agri_upload_flight_status", "flight_id", "status"),)


class AgricultureMediaQualityException(Base):
    """Durable post-flight media reconciliation exception."""

    __tablename__ = "agriculture_media_quality_exceptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_media_manifests.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_upload_sessions.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="error")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_agri_media_exception_flight_status", "flight_id", "status"),
        UniqueConstraint("flight_id", "media_id", "upload_id", "code", "status", name="uq_agri_media_exception_open"),
    )


class AgricultureFrameLineage(Base):
    __tablename__ = "agriculture_frame_lineage"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("agriculture_media_manifests.id", ondelete="CASCADE"), index=True)
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    image_width: Mapped[int | None] = mapped_column(Integer)
    image_height: Mapped[int | None] = mapped_column(Integer)
    source_checksum: Mapped[str | None] = mapped_column(String(128))
    sampling_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    pose_interpolation_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unresolved")
    telemetry_sample_before_id: Mapped[int | None] = mapped_column(
        ForeignKey("agriculture_telemetry_samples.id", ondelete="SET NULL"), index=True
    )
    telemetry_sample_after_id: Mapped[int | None] = mapped_column(
        ForeignKey("agriculture_telemetry_samples.id", ondelete="SET NULL"), index=True
    )
    georef_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unresolved")
    georef_error_m: Mapped[float | None] = mapped_column(Float)
    gsd_cm: Mapped[float | None] = mapped_column(Float)
    footprint_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    footprint: Mapped[Any | None] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True))
    quality_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_artifact_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("media_id", "frame_index", name="uq_agri_frame_media_index"),
        CheckConstraint("pose_interpolation_status IN ('unresolved', 'exact', 'interpolated', 'extrapolated', 'unavailable')", name="ck_agri_frame_pose_status"),
        CheckConstraint("footprint IS NULL OR GeometryType(footprint) IN ('POLYGON', 'MULTIPOLYGON')", name="ck_agri_frame_footprint_type"),
        Index("idx_agri_frame_flight_time", "flight_id", "timestamp_utc"),
    )


class AgricultureTimelineBookmark(Base):
    """Operator bookmark and note anchored to a canonical frame lineage row."""

    __tablename__ = "agriculture_timeline_bookmarks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    frame_lineage_id: Mapped[str] = mapped_column(ForeignKey("agriculture_frame_lineage.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("flight_id", "frame_lineage_id", "created_by_user_id", name="uq_agri_timeline_bookmark_user_frame"),)


class AgricultureAnalysisRun(Base):
    __tablename__ = "agriculture_analysis_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    requested_analyses: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    analysis_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    input_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    calibration_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    input_checksum: Mapped[str | None] = mapped_column(String(128), index=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    baseline_flight_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="SET NULL"), index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audit_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    counters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    quality_gate: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("flight_id", "idempotency_key", name="uq_agri_run_flight_idempotency"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_agri_run_progress"),
        CheckConstraint("retry_count >= 0", name="ck_agri_run_retry_count"),
    )


class AgricultureCapabilityRelease(Base):
    """Agriculture-owned policy linking a capability to a canonical Vision artifact."""

    __tablename__ = "agriculture_capability_releases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    scope_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    capability_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    vision_model_version_id: Mapped[str] = mapped_column(
        ForeignKey("vision_model_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    sensor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rgb")
    crop_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    inference_profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_agri_capability_release_status",
        ),
        Index(
            "uq_agri_active_capability_release",
            "scope_key",
            "capability_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )


class AgricultureAnalysisVideoJob(Base):
    """Immutable link from one Agriculture capability input to Video inference."""

    __tablename__ = "agriculture_analysis_video_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capability_release_id: Mapped[str] = mapped_column(
        ForeignKey("agriculture_capability_releases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("video_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    video_job_id: Mapped[str] = mapped_column(
        ForeignKey("video_analysis_jobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inference_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "capability_id",
            "video_id",
            name="uq_agri_analysis_video_capability",
        ),
    )


class AgricultureAnalysisStage(Base):
    __tablename__ = "agriculture_analysis_stages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    input_checksum: Mapped[str | None] = mapped_column(String(128))
    output_checksum: Mapped[str | None] = mapped_column(String(128))
    execution_key: Mapped[str | None] = mapped_column(String(200))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    task_id: Mapped[str | None] = mapped_column(String(128), index=True)
    queue_name: Mapped[str | None] = mapped_column(String(128), index=True)
    retryable: Mapped[bool] = mapped_column(nullable=False, default=True)
    dead_letter: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_letter_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "stage_name", name="uq_agri_stage_run_name"),
        Index(
            "uq_agri_stage_execution_key",
            "execution_key",
            unique=True,
            postgresql_where=text("execution_key IS NOT NULL"),
        ),
    )


class AgricultureFrameQuality(Base):
    __tablename__ = "agriculture_frame_quality"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_media_manifests.id", ondelete="SET NULL"), index=True)
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    blur_score: Mapped[float | None] = mapped_column(Float)
    motion_score: Mapped[float | None] = mapped_column(Float)
    clipped_ratio: Mapped[float | None] = mapped_column(Float)
    black_ratio: Mapped[float | None] = mapped_column(Float)
    glare_ratio: Mapped[float | None] = mapped_column(Float)
    contrast_score: Mapped[float | None] = mapped_column(Float)
    noise_score: Mapped[float | None] = mapped_column(Float)
    duplicate_score: Mapped[float | None] = mapped_column(Float)
    telemetry_quality: Mapped[str | None] = mapped_column(String(24))
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="warning", index=True)
    evidence_path: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", "frame_index", name="uq_agri_quality_run_frame"),)


class AgricultureObservation(Base):
    __tablename__ = "agriculture_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    observation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    geometry_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    geometry: Mapped[Any | None] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True))
    zone_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="observation")
    georef_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unresolved", index=True)
    area_m2: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    first_detected: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_detected: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trend: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    sensor_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(160))
    review_state: Mapped[str] = mapped_column(String(24), nullable=False, default="unreviewed", index=True)
    review_label: Mapped[str | None] = mapped_column(String(128))
    review_note: Mapped[str | None] = mapped_column(Text)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_into_id: Mapped[str | None] = mapped_column(
        ForeignKey("agriculture_observations.id", ondelete="SET NULL"),
        index=True,
    )
    split_from_id: Mapped[str | None] = mapped_column(
        ForeignKey("agriculture_observations.id", ondelete="SET NULL"),
        index=True,
    )
    member_observation_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_agri_observation_run_type", "run_id", "observation_type"),
        Index(
            "idx_agri_observation_run_severity_id", "run_id", "severity", "id"
        ),
        Index(
            "idx_agri_observation_run_type_severity_id",
            "run_id",
            "observation_type",
            "severity",
            "id",
        ),
        CheckConstraint("zone_kind IN ('observation', 'management_zone', 'prescription_zone')", name="ck_agri_observation_zone_kind"),
        CheckConstraint("geometry IS NULL OR ST_SRID(geometry) = 4326", name="ck_agri_observation_geometry_srid"),
        CheckConstraint("geometry IS NULL OR GeometryType(geometry) IN ('POLYGON', 'MULTIPOLYGON')", name="ck_agri_observation_geometry_type"),
        CheckConstraint("area_m2 IS NULL OR area_m2 >= 0", name="ck_agri_observation_area"),
        CheckConstraint("severity >= 0 AND severity <= 1", name="ck_agri_observation_severity"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_agri_observation_confidence"),
    )


class AgricultureObservationEvidence(Base):
    """Canonical source link for an observation, independent of legacy JSON evidence IDs."""

    __tablename__ = "agriculture_observation_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    observation_id: Mapped[str] = mapped_column(ForeignKey("agriculture_observations.id", ondelete="CASCADE"), index=True)
    detection_id: Mapped[str | None] = mapped_column(ForeignKey("video_detections.id", ondelete="SET NULL"), index=True)
    frame_lineage_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_frame_lineage.id", ondelete="SET NULL"), index=True)
    media_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_media_manifests.id", ondelete="SET NULL"), index=True)
    source_video_id: Mapped[str | None] = mapped_column(ForeignKey("video_assets.id", ondelete="SET NULL"), index=True)
    evidence_path: Mapped[str | None] = mapped_column(Text)
    frame_index: Mapped[int | None] = mapped_column(Integer)
    timestamp_seconds: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("observation_id", "detection_id", name="uq_agri_observation_detection"),)


class AgricultureAnalysisLayer(Base):
    __tablename__ = "agriculture_analysis_layers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    layer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ready")
    geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", "layer_name", name="uq_agri_layer_run_name"),)


class AgricultureHealthBaseline(Base):
    __tablename__ = "agriculture_health_baselines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    profile_key: Mapped[str] = mapped_column(String(128), nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.25)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("field_id", "profile_key", name="uq_agri_baseline_field_profile"),)
