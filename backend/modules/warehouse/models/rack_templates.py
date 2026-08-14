"""Warehouse ORM — rack templates."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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

if TYPE_CHECKING:
    from .maps import WarehouseMap


class WarehouseRackTemplate(Base):
    __tablename__ = "warehouse_rack_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rack_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="rack_templates")
    versions: Mapped[list[WarehouseRackTemplateVersion]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("warehouse_map_id", "name", name="uq_warehouse_rack_template_name"),
        Index("idx_warehouse_rack_template_map_active", "warehouse_map_id", "active"),
    )


class WarehouseRackTemplateVersion(Base):
    __tablename__ = "warehouse_rack_template_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_rack_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    bay_width_m: Mapped[float] = mapped_column(Float, nullable=False)
    shelf_heights_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    bin_pitch_m: Mapped[float] = mapped_column(Float, nullable=False)
    bin_count: Mapped[int | None] = mapped_column(Integer)
    left_face_naming: Mapped[str] = mapped_column(
        String(32), nullable=False, default="left_to_right"
    )
    right_face_naming: Mapped[str] = mapped_column(
        String(32), nullable=False, default="right_to_left"
    )
    barcode_scan_side: Mapped[str] = mapped_column(String(32), nullable=False, default="front")
    preferred_standoff_m: Mapped[float] = mapped_column(Float, nullable=False, default=1.2)
    min_scanner_angle_deg: Mapped[float] = mapped_column(Float, nullable=False, default=20.0)
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[WarehouseRackTemplate] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_warehouse_rack_template_version"),
        CheckConstraint(
            "status IN ('draft', 'active', 'superseded')",
            name="ck_warehouse_rack_template_version_status",
        ),
        CheckConstraint("bay_width_m > 0", name="ck_warehouse_rack_template_bay_width"),
        CheckConstraint("bin_pitch_m > 0", name="ck_warehouse_rack_template_bin_pitch"),
        CheckConstraint(
            "bin_count IS NULL OR bin_count > 0",
            name="ck_warehouse_rack_template_bin_count",
        ),
    )


__all__ = ["WarehouseRackTemplate", "WarehouseRackTemplateVersion"]
