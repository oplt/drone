"""Release 5 safety, action, prescription, export and audit records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


def p5_id() -> str:
    return str(uuid.uuid4())


class AgricultureInspectionAction(Base):
    __tablename__ = "agriculture_inspection_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p5_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    area_m2: Mapped[float | None] = mapped_column(Float)
    issue_type: Mapped[str] = mapped_column(String(96), nullable=False)
    geometry_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    waypoint_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    route_constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureAgronomyRule(Base):
    __tablename__ = "agriculture_agronomy_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p5_id)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    rule_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(128), nullable=False)
    crop_type: Mapped[str | None] = mapped_column(String(96))
    issue_type: Mapped[str] = mapped_column(String(96), nullable=False)
    action_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="inspection_only")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    regulatory_reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("org_id", "rule_key", "version", name="uq_agri_rule_org_key_version"),)


class AgriculturePrescriptionDraft(Base):
    __tablename__ = "agriculture_prescription_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p5_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_agronomy_rules.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    zones: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    rule_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", "rule_id", name="uq_agri_prescription_run_rule"),)


class AgricultureExportJob(Base):
    __tablename__ = "agriculture_export_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p5_id)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    artifact_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    checksum: Mapped[str | None] = mapped_column(String(128))
    content_type: Mapped[str | None] = mapped_column(String(128))
    source_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureReportSnapshot(Base):
    """Immutable, reproducible report input captured from an analysis run."""

    __tablename__ = "agriculture_report_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p5_id)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    template_key: Mapped[str] = mapped_column(String(64), nullable=False, default="standard")
    template_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_agri_report_snapshot_run_time", "run_id", "created_at"),)


class AgricultureGovernanceAudit(Base):
    __tablename__ = "agriculture_governance_audits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p5_id)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str | None] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_agri_governance_entity_time", "entity_type", "entity_id", "created_at"),)


class AgricultureExportAccessAudit(Base):
    __tablename__ = "agriculture_export_access_audits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p5_id)
    export_id: Mapped[str] = mapped_column(ForeignKey("agriculture_export_jobs.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureFieldOutcome(Base):
    """Field/scout outcome feedback linked to a finding for later evaluation."""

    __tablename__ = "agriculture_field_outcomes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p5_id)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("agriculture_observations.id", ondelete="CASCADE"), index=True)
    outcome_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(160))
    capability_release_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_agri_field_outcome_run_obs", "run_id", "observation_id", "created_at"),
    )
