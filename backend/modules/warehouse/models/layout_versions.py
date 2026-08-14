"""Warehouse ORM — layout versions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class WarehouseLayoutVersion(Base):
    __tablename__ = "warehouse_layout_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coordinate_frame_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    map_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_models.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    artifact_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_scan_artifact_sets.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    input_checksum: Mapped[str | None] = mapped_column(String(64))
    algorithm_version: Mapped[str | None] = mapped_column(String(64))
    provenance_status: Mapped[str] = mapped_column(
        String(24), default="auto", nullable=False, index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("warehouse_map_id", "version", name="uq_warehouse_layout_version"),
        CheckConstraint(
            "status IN ('draft', 'locked', 'superseded')",
            name="ck_warehouse_layout_version_status",
        ),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_layout_provenance",
        ),
        Index(
            "uq_warehouse_layout_locked",
            "warehouse_map_id",
            unique=True,
            postgresql_where=text("status = 'locked'"),
        ),
    )


__all__ = ["WarehouseLayoutVersion"]
