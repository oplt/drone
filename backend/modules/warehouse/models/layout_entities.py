"""Warehouse ORM — layout hierarchy entities and candidates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class WarehouseAisle(Base):
    __tablename__ = "warehouse_aisles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    layout_version_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_rack_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_artifact_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_scan_artifact_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence_breakdown_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    fit_residual_m: Mapped[float | None] = mapped_column(Float)
    observed_point_count: Mapped[int | None] = mapped_column(Integer)
    coverage_ratio: Mapped[float | None] = mapped_column(Float)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance_status: Mapped[str] = mapped_column(String(24), default="auto", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("layout_version_id", "code", name="uq_warehouse_aisle_code"),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_aisle_provenance",
        ),
    )


class WarehouseRack(Base):
    __tablename__ = "warehouse_racks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aisle_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_aisles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_rack_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    template_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_rack_template_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_artifact_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_scan_artifact_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fitted_transform_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    template_fit_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    face_plane_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence_breakdown_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    fit_residual_m: Mapped[float | None] = mapped_column(Float)
    observed_point_count: Mapped[int | None] = mapped_column(Integer)
    coverage_ratio: Mapped[float | None] = mapped_column(Float)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance_status: Mapped[str] = mapped_column(String(24), default="auto", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("aisle_id", "code", name="uq_warehouse_rack_code"),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_rack_provenance",
        ),
    )


class WarehouseShelf(Base):
    __tablename__ = "warehouse_shelves"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rack_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_racks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_rack_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_artifact_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_scan_artifact_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence_breakdown_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    fit_residual_m: Mapped[float | None] = mapped_column(Float)
    observed_point_count: Mapped[int | None] = mapped_column(Integer)
    coverage_ratio: Mapped[float | None] = mapped_column(Float)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance_status: Mapped[str] = mapped_column(String(24), default="auto", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("rack_id", "level", name="uq_warehouse_shelf_level"),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_shelf_provenance",
        ),
    )


class WarehouseBin(Base):
    __tablename__ = "warehouse_bins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shelf_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_shelves.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_rack_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_artifact_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_scan_artifact_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    center_local_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    volume_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence_breakdown_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    fit_residual_m: Mapped[float | None] = mapped_column(Float)
    observed_point_count: Mapped[int | None] = mapped_column(Integer)
    coverage_ratio: Mapped[float | None] = mapped_column(Float)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance_status: Mapped[str] = mapped_column(String(24), default="auto", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("shelf_id", "code", name="uq_warehouse_bin_code"),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_bin_provenance",
        ),
    )


class WarehouseSafetyZone(Base):
    __tablename__ = "warehouse_safety_zones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    layout_version_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    min_z_m: Mapped[float | None] = mapped_column(Float)
    max_z_m: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_rack_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_artifact_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_scan_artifact_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence_breakdown_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    fit_residual_m: Mapped[float | None] = mapped_column(Float)
    observed_point_count: Mapped[int | None] = mapped_column(Integer)
    coverage_ratio: Mapped[float | None] = mapped_column(Float)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("layout_version_id", "code", name="uq_warehouse_safety_zone_code"),
        CheckConstraint(
            "kind IN ('no_fly', 'keep_out', 'slow', 'landing')",
            name="ck_warehouse_safety_zone_kind",
        ),
    )


class WarehouseLayoutCandidate(Base):
    __tablename__ = "warehouse_layout_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layout_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    entity_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(String(256), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="provisional", nullable=False, index=True
    )
    displacement_m: Mapped[float | None] = mapped_column(Float)
    source_sequence: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "warehouse_map_id",
            "identity_key",
            "source_sequence",
            name="uq_warehouse_layout_candidate_observation",
        ),
        CheckConstraint(
            "entity_kind IN ('aisle', 'rack', 'shelf', 'bin', 'zone', 'inspection_target')",
            name="ck_warehouse_layout_candidate_kind",
        ),
        CheckConstraint(
            "status IN ('provisional', 'needs_review', 'accepted', 'rejected')",
            name="ck_warehouse_layout_candidate_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_layout_candidate_confidence"
        ),
    )


__all__ = [
    "WarehouseAisle",
    "WarehouseBin",
    "WarehouseLayoutCandidate",
    "WarehouseRack",
    "WarehouseSafetyZone",
    "WarehouseShelf",
]
