from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class OperatorCertification(Base):
    """Regulatory certification held by a drone operator (FAA Part 107, etc.)."""

    __tablename__ = "operator_certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    cert_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # FAA_PART_107 | ICAO_RPAS | OTHER
    cert_number: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issuing_authority: Mapped[str | None] = mapped_column(String(255))
    document_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("idx_operator_cert_user_type", "user_id", "cert_type"),)


class DeviceReadiness(Base):
    """Per-device airworthiness and inspection tracking."""

    __tablename__ = "device_readiness"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_inspection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_inspection_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="airworthy"
    )  # airworthy | grounded | limited
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

    __table_args__ = (
        UniqueConstraint("device_id", "org_id", name="uq_device_readiness_device_org"),
        Index("idx_device_readiness_org_status", "org_id", "status"),
    )
