from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


class VideoAsset(Base):
    __tablename__ = "video_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    field_id: Mapped[int | None] = mapped_column(
        ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)

    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capture_time_source: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unknown"
    )
    capture_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capture_time_uncertainty_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    sync_offset_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reanalysis_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    capture_metadata_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    jobs: Mapped[list[VideoAnalysisJob]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )


class VideoAnalysisJob(Base):
    __tablename__ = "video_analysis_jobs"
    __table_args__ = (
        CheckConstraint("tracker_type IN ('bytetrack')", name="ck_video_analysis_tracker_type"),
        CheckConstraint("attempt >= 0", name="ck_video_analysis_job_attempt_nonnegative"),
        Index("ix_video_analysis_jobs_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("video_assets.id", ondelete="CASCADE"), index=True
    )
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    orchestration_key: Mapped[str | None] = mapped_column(
        String(160), nullable=True, unique=True, index=True
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_name: Mapped[str] = mapped_column(String(128), nullable=False, default="yolo26s.pt")
    model_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("vision_model_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    small_object_mode: Mapped[bool] = mapped_column(nullable=False, default=False)
    tracking_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    tracker_type: Mapped[str] = mapped_column(String(32), nullable=False, default="bytetrack")
    model_version: Mapped[str] = mapped_column(String(160), nullable=False, default="unknown")
    loaded_model_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frame_stride_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)
    frames_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_decoded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_persisted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_dropped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_inference_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    terminal_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    terminal_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_timings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capture_metadata_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    video: Mapped[VideoAsset] = relationship(back_populates="jobs")
    detections: Mapped[list[VideoDetection]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class VideoDetection(Base):
    __tablename__ = "video_detections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("video_analysis_jobs.id", ondelete="CASCADE"), index=True
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("video_assets.id", ondelete="CASCADE"), index=True
    )
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_seconds: Mapped[float] = mapped_column(Float, nullable=False)

    label: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[float] = mapped_column(Float, nullable=False)
    y2: Mapped[float] = mapped_column(Float, nullable=False)

    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)

    evidence_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_object_id: Mapped[str | None] = mapped_column(
        ForeignKey("video_storage_objects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[VideoAnalysisJob] = relationship(back_populates="detections")
    storage_object: Mapped[StorageObject | None] = relationship()


class StorageObject(Base):
    __tablename__ = "video_storage_objects"
    __table_args__ = (
        CheckConstraint(
            "state IN ('staged', 'final', 'orphan', 'deleted')",
            name="ck_video_storage_object_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="staged", index=True)
    retention_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="analysis_evidence"
    )
    backend_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


Index("ix_video_detections_job_time", VideoDetection.job_id, VideoDetection.timestamp_seconds)
Index("ix_video_detections_mission_label", VideoDetection.mission_id, VideoDetection.label)
