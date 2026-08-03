from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base
from backend.modules.agriculture.models import new_id


class AgricultureMissionPlan(Base):
    __tablename__ = "agriculture_mission_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    source_plan_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_mission_plans.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    plan_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    route_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    estimates_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    validation_errors_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    grid_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    planner_version: Mapped[str] = mapped_column(String(64), nullable=False, default="agriculture-grid.v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'validated', 'committed', 'superseded', 'invalid')", name="ck_agri_plan_status"),
        Index("idx_agri_plan_field_created", "field_id", "created_at"),
    )


class AgricultureMissionPlanRevision(Base):
    __tablename__ = "agriculture_mission_plan_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("agriculture_mission_plans.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    planner_version: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    grid_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    estimates_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("uq_agri_plan_revision", "plan_id", "revision", unique=True),)


class AgriculturePreflightSnapshot(Base):
    __tablename__ = "agriculture_preflight_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("agriculture_mission_plans.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="SET NULL"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="blocked", index=True)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evaluator_version: Mapped[str] = mapped_column(String(64), nullable=False, default="agriculture-preflight.v2")
    signoff_hash: Mapped[str | None] = mapped_column(String(128))
    operator_notes: Mapped[str | None] = mapped_column(Text)
    checks_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(Integer)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('blocked', 'warning', 'pass', 'expired')", name="ck_agri_preflight_status"),
        Index("idx_agri_preflight_plan_created", "plan_id", "created_at"),
    )
