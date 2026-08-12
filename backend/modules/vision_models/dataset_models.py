from __future__ import annotations

import uuid
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
    from backend.modules.vision_models.training_models import TrainingRun, VisionModel


def new_uuid() -> str:
    return str(uuid.uuid4())


class VisionProject(Base):
    __tablename__ = "vision_projects"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('detection', 'instance_segmentation')",
            name="ck_vision_project_task_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    crop: Mapped[str] = mapped_column(String(120), nullable=False)
    task_type: Mapped[str] = mapped_column(String(40), nullable=False, default="detection")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    classes: Mapped[list[VisionClass]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="VisionClass.class_index",
        lazy="selectin",
    )
    datasets: Mapped[list[DatasetVersion]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    training_runs: Mapped[list[TrainingRun]] = relationship(back_populates="project")
    models: Mapped[list[VisionModel]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class VisionClass(Base):
    __tablename__ = "vision_classes"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_vision_class_project_name"),
        UniqueConstraint("project_id", "class_index", name="uq_vision_class_project_index"),
        CheckConstraint("class_index >= 0", name="ck_vision_class_index_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("vision_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    class_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    project: Mapped[VisionProject] = relationship(back_populates="classes")


class DatasetVersion(Base):
    __tablename__ = "vision_datasets"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_vision_dataset_version"),
        CheckConstraint("version > 0", name="ck_vision_dataset_version_positive"),
        CheckConstraint("status IN ('draft', 'locked')", name="ck_vision_dataset_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("vision_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    labeled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    train_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    val_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manifest_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped[VisionProject] = relationship(back_populates="datasets")
    images: Mapped[list[DatasetImage]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    training_runs: Mapped[list[TrainingRun]] = relationship(back_populates="dataset")

    @property
    def selected_count(self) -> int:
        return self.train_count + self.val_count + self.test_count


class DatasetImage(Base):
    __tablename__ = "vision_dataset_images"
    __table_args__ = (
        UniqueConstraint("dataset_id", "sha256", name="uq_vision_image_dataset_sha256"),
        Index("ix_vision_image_dataset_split", "dataset_id", "split"),
        Index("ix_vision_image_dataset_status", "dataset_id", "annotation_status"),
        Index("ix_vision_image_source_group", "dataset_id", "source_group"),
        CheckConstraint(
            "split IS NULL OR split IN ('train', 'val', 'test')",
            name="ck_vision_image_split",
        ),
        CheckConstraint(
            "annotation_status IN ('unlabeled', 'labeled', 'reviewed')",
            name="ck_vision_image_annotation_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("vision_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    source_group: Mapped[str] = mapped_column(String(160), nullable=False)
    source_video_id: Mapped[str | None] = mapped_column(
        ForeignKey("video_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mission_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    field_id: Mapped[int | None] = mapped_column(
        ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    split: Mapped[str | None] = mapped_column(String(8), nullable=True)
    annotation_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unlabeled")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    dataset: Mapped[DatasetVersion] = relationship(back_populates="images")
    annotations: Mapped[list[Annotation]] = relationship(
        back_populates="image", cascade="all, delete-orphan", lazy="selectin"
    )


class Annotation(Base):
    __tablename__ = "vision_annotations"
    __table_args__ = (
        CheckConstraint("annotation_type = 'bbox'", name="ck_vision_annotation_type"),
        CheckConstraint(
            "source IN ('manual', 'auto', 'imported')", name="ck_vision_annotation_source"
        ),
        CheckConstraint("x1 >= 0 AND x1 < x2", name="ck_vision_annotation_x"),
        CheckConstraint("y1 >= 0 AND y1 < y2", name="ck_vision_annotation_y"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    image_id: Mapped[str] = mapped_column(
        ForeignKey("vision_dataset_images.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_id: Mapped[str] = mapped_column(
        ForeignKey("vision_classes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    annotation_type: Mapped[str] = mapped_column(String(24), nullable=False, default="bbox")
    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[float] = mapped_column(Float, nullable=False)
    y2: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    segmentation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    image: Mapped[DatasetImage] = relationship(back_populates="annotations")
