from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base


class MissionTemplate(Base):
    """Saved mission configuration for one-click rerun and scheduled dispatch."""

    __tablename__ = "mission_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    mission_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preflight_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Null schedule means manual execution only.
    schedule_cron: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    runs: Mapped[list[ScheduledRun]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_mission_template_org_slug"),
        Index("idx_mission_template_org_active", "org_id", "is_active"),
    )


class ScheduledRun(Base):
    """Record of each execution of a MissionTemplate (scheduled or manual)."""

    __tablename__ = "scheduled_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("mission_templates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    triggered_by: Mapped[str] = mapped_column(String(16), nullable=False)  # "schedule" | "manual"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[MissionTemplate] = relationship(back_populates="runs")

    __table_args__ = (Index("idx_scheduled_run_template_time", "template_id", "created_at"),)


class OutboxEvent(Base):
    """Durable event awaiting asynchronous publication."""

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_outbox_pending_available", "status", "available_at"),)
