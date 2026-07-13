from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
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

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    jobs: Mapped[list[VideoAnalysisJob]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )


class VideoAnalysisJob(Base):
    __tablename__ = "video_analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("video_assets.id", ondelete="CASCADE"), index=True
    )
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_name: Mapped[str] = mapped_column(String(128), nullable=False, default="yolo26s.pt")
    model_version: Mapped[str] = mapped_column(String(160), nullable=False, default="unknown")
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frame_stride_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)
    frames_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_dropped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frames_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_inference_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

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
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[VideoAnalysisJob] = relationship(back_populates="detections")


Index("ix_video_detections_job_time", VideoDetection.job_id, VideoDetection.timestamp_seconds)
Index("ix_video_detections_mission_label", VideoDetection.mission_id, VideoDetection.label)
