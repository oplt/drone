"""Durable, human-reviewed geospatial intervention zones."""

from __future__ import annotations

import uuid
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class AgricultureInterventionZone(Base):
    __tablename__ = "agriculture_intervention_zones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    flight_id: Mapped[str] = mapped_column(
        ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    source_observation_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    model_versions: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed", index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected')",
            name="ck_agri_intervention_zone_status",
        ),
        CheckConstraint("area_m2 > 0", name="ck_agri_intervention_zone_area"),
        Index("idx_agri_intervention_run_status", "run_id", "status"),
    )
