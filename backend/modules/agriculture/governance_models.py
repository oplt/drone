"""Auditable, evidence-grounded agriculture assistant runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


def governance_id() -> str:
    return str(uuid.uuid4())


class AgricultureAssistantRun(Base):
    __tablename__ = "agriculture_assistant_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=governance_id)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="fallback", index=True)
    decision_status: Mapped[str] = mapped_column(String(32), nullable=False, default="provider_unavailable")
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="agriculture_governance_v1")
    prompt_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    context_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    question_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    deterministic_rules: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    citations: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    limitations: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="high")
    requires_human_approval: Mapped[bool] = mapped_column(nullable=False, default=True)
    abstained: Mapped[bool] = mapped_column(nullable=False, default=True)
    profile_id: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(256))
    error_code: Mapped[str | None] = mapped_column(String(128))
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_agri_assistant_run_time", "run_id", "created_at"),)
