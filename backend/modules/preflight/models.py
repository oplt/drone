from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base

if TYPE_CHECKING:
    from backend.modules.missions.runtime_models import MissionRuntime


class PreflightRun(Base):
    """Persistent record of a single preflight check execution.

    Replaces ad-hoc ``preflight_report`` FlightEvent rows with a first-class
    table so results are structured, queryable, and linkable to a
    ``MissionRuntime``.
    """

    __tablename__ = "preflight_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # UUID assigned at run start; matches the ``preflight_run_id`` stored in
    # ``MissionRuntimeRecord`` and ``MissionRuntime``.
    run_uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Optional link to the flight record if one already exists at preflight time.
    flight_id: Mapped[int | None] = mapped_column(
        ForeignKey("flights.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Operator who triggered the preflight (nullable: automated runs).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # --- Mission context ---
    mission_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mission_name: Mapped[str | None] = mapped_column(String(255))

    # SHA-256 of the mission payload at the time of preflight — used to validate
    # that the mission launched matches the payload that was preflight-checked.
    mission_fingerprint: Mapped[str | None] = mapped_column(String(64))

    # Wall-clock expiry — preflight tokens are only valid for PREFLIGHT_RUN_TTL_SECONDS.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Vehicle identifier reported by the drone at preflight time.
    vehicle_id: Mapped[str | None] = mapped_column(String(64))

    # --- Result ---
    # One of: PASS | WARN | FAIL
    overall_status: Mapped[str] = mapped_column(String(8), nullable=False, index=True)

    # Structured check results — matches PreflightReport.base_checks / mission_checks.
    # Each item: {"name": str, "status": str, "message": str|null}
    base_checks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    mission_checks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    # Names of checks with status FAIL that blocked launch.
    critical_failures: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    # Aggregated counts: {passed, warned, failed, skipped}
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Whether the operator explicitly acknowledged warnings and proceeded.
    operator_acknowledged_warnings: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # --- Timestamps ---
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # --- Relationships ---
    mission_runtime: Mapped[MissionRuntime | None] = relationship(
        back_populates="preflight_run",
        foreign_keys="MissionRuntime.preflight_run_id",
    )

    __table_args__ = (
        Index("idx_preflight_run_status_created", "overall_status", "created_at"),
        Index("idx_preflight_run_flight", "flight_id"),
    )
