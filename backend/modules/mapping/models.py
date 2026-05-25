from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
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
    from backend.modules.fields.models import Field


class FieldModel(Base):
    __tablename__ = "field_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending"
    )  # pending|processing|ready|failed

    # data quality
    gsd_cm: Mapped[float | None] = mapped_column(Float)
    epsg: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    field: Mapped[Field] = relationship(back_populates="models")
    jobs: Mapped[list[MappingJob]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )
    assets: Mapped[list[Asset]] = relationship(back_populates="model", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("field_id", "version", name="uq_field_model_version"),
        Index("idx_field_model_status", "status"),
    )


class MappingJob(Base):
    __tablename__ = "mapping_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("field_models.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending"
    )  # pending|uploading|processing|ready|failed
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # external processor (WebODM task id etc.)
    processor: Mapped[str] = mapped_column(String(32), nullable=False, default="webodm")
    processor_task_id: Mapped[str | None] = mapped_column(String(64), index=True)

    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    model: Mapped[FieldModel] = relationship(back_populates="jobs")

    __table_args__ = (Index("idx_mapping_job_status", "status"),)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("field_models.id", ondelete="CASCADE"), index=True
    )

    type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # ORTHO_COG, DSM_COG, DTM_COG, TILESET_3D, POINTCLOUD, ...
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(128))

    # bbox for quick camera framing
    bbox: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=True,
    )

    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[FieldModel] = relationship(back_populates="assets")

    __table_args__ = (Index("idx_asset_model_type", "model_id", "type"),)
