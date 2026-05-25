from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class ComplianceRecord(Base):
    """FAA / LAANC compliance metadata for a mission runtime."""

    __tablename__ = "compliance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    mission_runtime_id: Mapped[int] = mapped_column(
        ForeignKey("mission_runtimes.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    remote_id_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )  # broadcast | off | unknown
    laanc_auth_number: Mapped[str | None] = mapped_column(String(64))
    laanc_auth_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preflight_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
