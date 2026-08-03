"""Auditable spectral, thermal and external-sensor input contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


def sensor_id() -> str:
    return str(uuid.uuid4())


class AgricultureSensorCalibration(Base):
    __tablename__ = "agriculture_sensor_calibrations"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    sensor_serial: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sensor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(160), nullable=False)
    calibration_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgricultureSpectralBand(Base):
    __tablename__ = "agriculture_spectral_bands"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=sensor_id)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("agriculture_media_manifests.id", ondelete="CASCADE"), index=True)
    band_name: Mapped[str] = mapped_column(String(32), nullable=False)
    wavelength_nm: Mapped[float | None] = mapped_column(Float)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    capture_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sensor_serial: Mapped[str | None] = mapped_column(String(128), index=True)
    calibration_id: Mapped[str | None] = mapped_column(ForeignKey("agriculture_sensor_calibrations.id", ondelete="SET NULL"), index=True)
    exposure_ms: Mapped[float | None] = mapped_column(Float)
    irradiance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    reflectance_panel: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    registration_transform: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    alignment_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unvalidated", index=True)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unvalidated", index=True)
    failure_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("media_id", "band_name", name="uq_agri_media_band"),)


class AgricultureSensorReading(Base):
    __tablename__ = "agriculture_sensor_readings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=sensor_id)
    flight_id: Mapped[str] = mapped_column(ForeignKey("agriculture_flights.id", ondelete="CASCADE"), index=True)
    sensor_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    sensor_serial: Mapped[str | None] = mapped_column(String(128), index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    scope_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    units: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stale_after_seconds: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_agri_sensor_reading_flight_time", "flight_id", "timestamp_utc"), Index("idx_agri_sensor_reading_type", "sensor_type"))


class AgricultureFusionResult(Base):
    __tablename__ = "agriculture_fusion_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=sensor_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), index=True)
    layer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_measured", index=True)
    measured: Mapped[bool] = mapped_column(nullable=False, default=False)
    units: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    required_inputs: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source_timestamps: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    failure_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", "layer_name", name="uq_agri_fusion_run_layer"),)
