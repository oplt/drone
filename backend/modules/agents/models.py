from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from backend.core.database.base import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_runtime_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    agent_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    llm_task: Mapped[str] = mapped_column(String(80), nullable=False)
    profile_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    prompt_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    response_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_result: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("idx_agent_runs_mission_agent", "mission_runtime_id", "agent_id"),
    )
