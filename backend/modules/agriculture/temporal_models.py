"""Temporal comparison, review governance, dataset and model-evaluation records."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


def temporal_id() -> str:
    return str(uuid.uuid4())


class AgricultureFlightAlignment(Base):
    __tablename__ = "agriculture_flight_alignments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    current_flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    reference_flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    method: Mapped[str] = mapped_column(String(64), nullable=False, default="field_boundary")
    alignment_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overlap_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    transform: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    failure_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("current_flight_id", "reference_flight_id", name="uq_agri_alignment_pair"),)


class AgricultureObservationChange(Base):
    __tablename__ = "agriculture_observation_changes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    current_flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    reference_flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    current_observation_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_observations.id", ondelete="CASCADE"), index=True)
    previous_observation_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_observations.id", ondelete="SET NULL"), index=True)
    observation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    geometry_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    reference_geometry_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    area_m2: Mapped[float | None] = mapped_column(Float)
    delta_area_m2: Mapped[float | None] = mapped_column(Float)
    delta_intensity: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("current_flight_id", "reference_flight_id", "current_observation_id", "previous_observation_id", name="uq_agri_change_pair"),
        Index("idx_agri_change_current_type", "current_flight_id", "observation_type"),
    )


class AgricultureReviewAudit(Base):
    __tablename__ = "agriculture_review_audits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    observation_id: Mapped[str] = mapped_column(ForeignKey("agriculture_observations.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(24))
    to_state: Mapped[str | None] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(Text)
    annotation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_agri_audit_observation_time", "observation_id", "created_at"),)


class AgricultureObservationAnnotation(Base):
    __tablename__ = "agriculture_observation_annotations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    observation_id: Mapped[str] = mapped_column(ForeignKey("agriculture_observations.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    geometry_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("observation_id", "version", name="uq_agri_annotation_version"),)


class AgricultureObservationFeedback(Base):
    """Non-destructive reviewer correction/disagreement awaiting a decision."""

    __tablename__ = "agriculture_observation_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    observation_id: Mapped[str] = mapped_column(ForeignKey("agriculture_observations.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    feedback_type: Mapped[str] = mapped_column(String(24), nullable=False, default="correction", index=True)
    proposed_label: Mapped[str | None] = mapped_column(String(128))
    proposed_severity: Mapped[float | None] = mapped_column(Float)
    proposed_zone_kind: Mapped[str | None] = mapped_column(String(24))
    proposed_geometry_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="submitted", index=True)
    decision_note: Mapped[str | None] = mapped_column(Text)
    annotation_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_observation_annotations.id", ondelete="SET NULL"), index=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("feedback_type IN ('correction', 'disagreement', 'comment')", name="ck_agri_feedback_type"),
        CheckConstraint("status IN ('submitted', 'accepted', 'rejected')", name="ck_agri_feedback_status"),
        CheckConstraint("proposed_severity IS NULL OR (proposed_severity >= 0 AND proposed_severity <= 1)", name="ck_agri_feedback_severity"),
    )


class AgricultureDatasetExport(Base):
    __tablename__ = "agriculture_dataset_exports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    dataset_key: Mapped[str] = mapped_column(String(128), index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="export")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureDatasetItem(Base):
    __tablename__ = "agriculture_dataset_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    export_id: Mapped[str] = mapped_column(ForeignKey("agriculture_dataset_exports.id", ondelete="CASCADE"), index=True)
    annotation_id: Mapped[str] = mapped_column(ForeignKey("agriculture_observation_annotations.id", ondelete="CASCADE"), index=True)
    feedback_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_observation_feedback.id", ondelete="SET NULL"), index=True)
    split: Mapped[str] = mapped_column(String(16), nullable=False, default="train")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureModelVersion(Base):
    __tablename__ = "agriculture_model_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    task: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="candidate", index=True)
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    dataset_key: Mapped[str | None] = mapped_column(String(128))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureModelQualityReport(Base):
    __tablename__ = "agriculture_model_quality_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=temporal_id)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("agriculture_model_versions.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, default="all")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    slices: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    drift: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evaluation_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
