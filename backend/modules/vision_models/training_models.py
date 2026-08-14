from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base
from backend.modules.vision_models.dataset_models import (
    DatasetVersion,
    VisionProject,
    new_uuid,
)


class VisionStorageObject(Base):
    """Managed artifact metadata for Vision weights and evaluation files."""

    __tablename__ = "vision_storage_objects"
    __table_args__ = (
        CheckConstraint(
            "state IN ('staged', 'final', 'orphan', 'deleted')",
            name="ck_vision_storage_object_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="staged", index=True)
    retention_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="model_artifact"
    )
    backend_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TrainingRun(Base):
    __tablename__ = "vision_training_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'cancelling', 'completed', 'failed', 'cancelled')",
            name="ck_vision_training_status",
        ),
        CheckConstraint("attempt >= 0", name="ck_vision_training_attempt_nonnegative"),
        Index(
            "uq_vision_one_active_training_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'cancelling')"),
            sqlite_where=text("status IN ('queued', 'running', 'cancelling')"),
        ),
        Index("ix_vision_training_lease_expires_at", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("vision_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("vision_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    trainer: Mapped[str] = mapped_column(String(40), nullable=False, default="ultralytics")
    base_model: Mapped[str] = mapped_column(String(120), nullable=False)
    preset: Mapped[str] = mapped_column(String(24), nullable=False, default="balanced")
    epochs: Mapped[int] = mapped_column(Integer, nullable=False)
    image_size: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    device: Mapped[str] = mapped_column(String(24), nullable=False, default="auto")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    current_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    queue_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminal_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    terminal_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped[VisionProject] = relationship(back_populates="training_runs")
    dataset: Mapped[DatasetVersion] = relationship(back_populates="training_runs")
    model_version: Mapped[ModelVersion | None] = relationship(back_populates="training_run")


class VisionModel(Base):
    __tablename__ = "vision_models"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_vision_model_project_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("vision_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    crop: Mapped[str] = mapped_column(String(120), nullable=False)
    task_type: Mapped[str] = mapped_column(String(40), nullable=False, default="detection")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped[VisionProject] = relationship(back_populates="models")
    versions: Mapped[list[ModelVersion]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="ModelVersion.version"
    )


class ModelVersion(Base):
    __tablename__ = "vision_model_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version", name="uq_vision_model_version"),
        UniqueConstraint("training_run_id", name="uq_vision_model_training_run"),
        CheckConstraint(
            "status IN ('candidate', 'production', 'archived')",
            name="ck_vision_model_version_status",
        ),
        Index("ix_vision_model_status", "model_id", "status"),
        Index(
            "uq_vision_one_production_version",
            "model_id",
            unique=True,
            postgresql_where=text("status = 'production'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    model_id: Mapped[str] = mapped_column(
        ForeignKey("vision_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    training_run_id: Mapped[str] = mapped_column(
        ForeignKey("vision_training_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("vision_datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    architecture: Mapped[str] = mapped_column(String(80), nullable=False)
    weights_uri: Mapped[str] = mapped_column(Text, nullable=False)
    classes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evaluation_artifacts: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_object_id: Mapped[str | None] = mapped_column(
        ForeignKey("vision_storage_objects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="candidate")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[VisionModel] = relationship(back_populates="versions")
    training_run: Mapped[TrainingRun] = relationship(back_populates="model_version")
    storage_object: Mapped[VisionStorageObject | None] = relationship()
