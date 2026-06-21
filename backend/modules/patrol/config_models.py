from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
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


class PatrolSite(Base):
    __tablename__ = "patrol_sites"
    __table_args__ = (
        UniqueConstraint("org_id", "field_id", name="uq_patrol_site_org_field"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    response_profiles: Mapped[list["PatrolResponseProfile"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
    )
    sensors: Mapped[list["PatrolSensor"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
    )
    field: Mapped["Field"] = relationship()


class PatrolResponseProfile(Base):
    __tablename__ = "patrol_response_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("patrol_sites.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    cruise_alt: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    speed_mps: Mapped[float] = mapped_column(Float, default=6.0, nullable=False)
    verification_loiter_s: Mapped[float] = mapped_column(Float, default=45.0, nullable=False)
    verification_radius_m: Mapped[float] = mapped_column(Float, default=18.0, nullable=False)
    track_target: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_label: Mapped[str | None] = mapped_column(String(120))
    search_grid_spacing_m: Mapped[float] = mapped_column(Float, default=40.0, nullable=False)
    search_grid_angle_deg: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ai_tasks: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    site: Mapped[PatrolSite] = relationship(back_populates="response_profiles")
    sensors: Mapped[list["PatrolSensor"]] = relationship(back_populates="response_profile")


class PatrolSensor(Base):
    __tablename__ = "patrol_sensors"
    __table_args__ = (
        UniqueConstraint("org_id", "external_sensor_id", name="uq_patrol_sensor_org_external_id"),
        Index("idx_patrol_sensor_org_enabled", "org_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("patrol_sites.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    response_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("patrol_response_profiles.id", ondelete="SET NULL"),
        index=True,
    )
    external_sensor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(32), default="generic_webhook", nullable=False)
    location_lonlat: Mapped[list[Any] | None] = mapped_column(JSON)
    connector_type: Mapped[str] = mapped_column(String(32), default="webhook", nullable=False)
    connector_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    site: Mapped[PatrolSite] = relationship(back_populates="sensors")
    response_profile: Mapped[PatrolResponseProfile | None] = relationship(back_populates="sensors")


class PatrolEventTriggerConfig(Base):
    __tablename__ = "patrol_event_trigger_configs"
    __table_args__ = (
        UniqueConstraint("org_id", "field_id", name="uq_patrol_event_trigger_org_field"),
        Index("idx_patrol_event_trigger_org_active", "org_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cruise_alt: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    speed_mps: Mapped[float] = mapped_column(Float, default=6.0, nullable=False)
    verification_loiter_s: Mapped[float] = mapped_column(Float, default=45.0, nullable=False)
    verification_radius_m: Mapped[float] = mapped_column(Float, default=18.0, nullable=False)
    track_target: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_label: Mapped[str | None] = mapped_column(String(120))
    search_grid_spacing_m: Mapped[float] = mapped_column(Float, default=40.0, nullable=False)
    search_grid_angle_deg: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ai_tasks: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    field: Mapped["Field"] = relationship()


class PatrolTriggerReceipt(Base):
    __tablename__ = "patrol_trigger_receipts"
    __table_args__ = (
        UniqueConstraint("org_id", "trigger_id", name="uq_patrol_trigger_receipt_org_trigger"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    trigger_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sensor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_flight_id: Mapped[str | None] = mapped_column(String(128))
    response_mode: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
