from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class ExportJob(Base):
    __tablename__ = "export_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    flight_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    download_url: Mapped[str | None] = mapped_column(String(2048))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(512))


# ---------------------------------------------------------------------------
# P3 — Platform & Growth models
# ---------------------------------------------------------------------------


class FieldDeliverable(Base):
    """Generated agronomy deliverable (GeoJSON, HTML summary, KML) with public share link."""

    __tablename__ = "field_deliverables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id", ondelete="CASCADE"), index=True, nullable=False
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # QA_CHECKLIST | HTML_SUMMARY | GEOJSON | KML
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    url: Mapped[str | None] = mapped_column(String(2048))  # S3 key or local path
    share_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("idx_field_deliverable_field_type", "field_id", "type"),)
