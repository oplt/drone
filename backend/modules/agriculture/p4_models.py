"""Release 4 crop insight records; model outputs remain reviewable and auditable."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


def p4_id() -> str:
    return str(uuid.uuid4())


class AgricultureCropRisk(Base):
    __tablename__ = "agriculture_crop_risks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p4_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    issue_type: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="candidate", index=True)
    crop_type: Mapped[str | None] = mapped_column(String(96))
    growth_stage: Mapped[str | None] = mapped_column(String(64))
    geometry_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trend: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    sensor_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    inspection_points: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    applicability: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(160))
    review_state: Mapped[str] = mapped_column(String(24), nullable=False, default="unreviewed", index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_agri_crop_risk_run_issue", "run_id", "issue_type"),)


class AgricultureGrowthMetric(Base):
    __tablename__ = "agriculture_growth_metrics"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p4_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    metric_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_measured", index=True)
    units: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source_timestamps: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", "metric_kind", name="uq_agri_growth_metric_run_kind"),)


class AgricultureGrowthStageEstimate(Base):
    __tablename__ = "agriculture_growth_stage_estimates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p4_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_measured")
    predicted_stage: Mapped[str | None] = mapped_column(String(64))
    candidates: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    human_stage: Mapped[str | None] = mapped_column(String(64))
    correction_note: Mapped[str | None] = mapped_column(Text)
    corrected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", name="uq_agri_stage_estimate_run"),)


class AgricultureHarvestLabel(Base):
    __tablename__ = "agriculture_harvest_labels"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p4_id)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    harvest_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    crop_type: Mapped[str] = mapped_column(String(96), nullable=False)
    variety: Mapped[str | None] = mapped_column(String(128))
    yield_value: Mapped[float] = mapped_column(Float, nullable=False)
    yield_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    area_ha: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureYieldForecast(Base):
    __tablename__ = "agriculture_yield_forecasts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=p4_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_applicable", index=True)
    units: Mapped[str | None] = mapped_column(String(32))
    forecast_range: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence_interval: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    applicability: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    harvest_label_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", name="uq_agri_yield_forecast_run"),)
