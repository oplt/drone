from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base


class Herd(Base):
    __tablename__ = "herds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Optional: link herd to a pasture geofence you already manage
    pasture_geofence_id: Mapped[int | None] = mapped_column(
        ForeignKey("geofences.id", ondelete="SET NULL"), index=True
    )

    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    animals: Mapped[list[Animal]] = relationship(
        back_populates="herd", cascade="all, delete-orphan"
    )


class Animal(Base):
    __tablename__ = "animals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    herd_id: Mapped[int] = mapped_column(ForeignKey("herds.id", ondelete="CASCADE"), index=True)

    # Collar identity (unique)
    collar_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    name: Mapped[str | None] = mapped_column(String(128))
    species: Mapped[str] = mapped_column(
        String(32), default="cow", nullable=False
    )  # cow/sheep/goat
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    herd: Mapped[Herd] = relationship(back_populates="animals")
    positions: Mapped[list[AnimalPosition]] = relationship(
        back_populates="animal", cascade="all, delete-orphan"
    )


class AnimalPosition(Base):
    """
    Time-series positions from collars.
    Use SRID 4326 point + lat/lon columns for convenience.
    """

    __tablename__ = "animal_positions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    animal_id: Mapped[int] = mapped_column(ForeignKey("animals.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    alt: Mapped[float | None] = mapped_column(Float)

    # Optional: collar derived speed/activity
    speed_mps: Mapped[float | None] = mapped_column(Float)
    activity: Mapped[float | None] = mapped_column(Float)

    # Geo point for PostGIS queries (distance, within pasture)
    point: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(32), default="collar", nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    animal: Mapped[Animal] = relationship(back_populates="positions")

    __table_args__ = (
        Index("idx_animal_pos_animal_time", "animal_id", "created_at"),
        Index("idx_animal_pos_animal_time_id", "animal_id", "created_at", "id"),
    )


class HerdTask(Base):
    """
    “Task” is your domain object: census, herd sweep, search & locate, predator scan, etc.
    This lets the Livestock page show a task list and statuses.
    """

    __tablename__ = "herd_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    herd_id: Mapped[int] = mapped_column(ForeignKey("herds.id", ondelete="CASCADE"), index=True)

    type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # e.g. "census", "search_locate", "herd_sweep"
    status: Mapped[str] = mapped_column(
        String(32), default="created", nullable=False
    )  # created/running/completed/failed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # optional link to your flights table if a drone mission is executed
    flight_id: Mapped[int | None] = mapped_column(
        ForeignKey("flights.id", ondelete="SET NULL"), index=True
    )

    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
