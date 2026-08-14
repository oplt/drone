from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class WorkflowEvent(Base):
    """Append-only event log used by SSE lifecycle streams.

    ``stream_id`` is an already-authorized aggregate (an analysis run or Vision
    project). ``subject_id`` identifies the concrete run when a project stream
    contains events for more than one training run.
    """

    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    domain: Mapped[str] = mapped_column(String(48), nullable=False)
    stream_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_workflow_events_stream_cursor", "domain", "stream_id", "id"),
        Index("ix_workflow_events_scope_cursor", "org_id", "user_id", "id"),
        Index(
            "uq_workflow_events_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
            sqlite_where=text("dedupe_key IS NOT NULL"),
        ),
    )
