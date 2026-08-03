"""Add agriculture spectral, thermal, external sensor and fusion records."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z3c4d5e6f7a8b"
down_revision: str | Sequence[str] | None = "y2b3c4d5e6f7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json(name: str, default: str = "{}") -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(f"'{default}'"))


def upgrade() -> None:
    op.create_table("agriculture_sensor_calibrations",
        sa.Column("id", sa.String(128), primary_key=True), sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")), sa.Column("sensor_serial", sa.String(128), nullable=False), sa.Column("sensor_type", sa.String(32), nullable=False), sa.Column("version", sa.String(160), nullable=False), sa.Column("calibration_kind", sa.String(64), nullable=False), _json("calibration_data"), sa.Column("checksum", sa.String(128), nullable=False), sa.Column("valid_from", sa.DateTime(timezone=True)), sa.Column("valid_until", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_sensor_calibration_org", "agriculture_sensor_calibrations", ["org_id"]); op.create_index("ix_agri_sensor_calibration_serial", "agriculture_sensor_calibrations", ["sensor_serial"])
    op.create_table("agriculture_spectral_bands",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("media_id", sa.String(64), sa.ForeignKey("agriculture_media_manifests.id", ondelete="CASCADE"), nullable=False), sa.Column("band_name", sa.String(32), nullable=False), sa.Column("wavelength_nm", sa.Float()), sa.Column("storage_key", sa.String(1024), nullable=False), sa.Column("checksum", sa.String(128), nullable=False), sa.Column("width", sa.Integer()), sa.Column("height", sa.Integer()), sa.Column("capture_timestamp", sa.DateTime(timezone=True)), sa.Column("sensor_serial", sa.String(128)), sa.Column("calibration_id", sa.String(128), sa.ForeignKey("agriculture_sensor_calibrations.id", ondelete="SET NULL")), sa.Column("exposure_ms", sa.Float()), _json("irradiance"), _json("reflectance_panel"), _json("registration_transform"), sa.Column("alignment_status", sa.String(24), nullable=False, server_default="unvalidated"), sa.Column("quality_status", sa.String(24), nullable=False, server_default="unvalidated"), sa.Column("failure_reasons", sa.JSON(), nullable=False, server_default="[]"), _json("metadata_json"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("media_id", "band_name", name="uq_agri_media_band"))
    for name, cols in (("ix_agri_spectral_flight", ["flight_id"]), ("ix_agri_spectral_media", ["media_id"]), ("ix_agri_spectral_calibration", ["calibration_id"]), ("ix_agri_spectral_alignment", ["alignment_status"]), ("ix_agri_spectral_quality", ["quality_status"]),): op.create_index(name, "agriculture_spectral_bands", cols)
    op.create_table("agriculture_sensor_readings",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("sensor_type", sa.String(48), nullable=False), sa.Column("source", sa.String(128), nullable=False), sa.Column("sensor_serial", sa.String(128)), sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False), sa.Column("lat", sa.Float()), sa.Column("lon", sa.Float()), _json("scope_geojson"), _json("values"), _json("units"), sa.Column("quality", sa.Float(), nullable=False, server_default="0"), sa.Column("stale_after_seconds", sa.Float()), _json("raw"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_sensor_reading_flight", "agriculture_sensor_readings", ["flight_id"]); op.create_index("ix_agri_sensor_reading_type", "agriculture_sensor_readings", ["sensor_type"]); op.create_index("ix_agri_sensor_reading_time", "agriculture_sensor_readings", ["timestamp_utc"])
    op.create_table("agriculture_fusion_results",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("layer_name", sa.String(64), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="not_measured"), sa.Column("measured", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("units", sa.String(64)), _json("summary"), sa.Column("required_inputs", sa.JSON(), nullable=False, server_default="[]"), sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("source_timestamps", sa.JSON(), nullable=False, server_default="[]"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), _json("uncertainty"), sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"), sa.Column("failure_reasons", sa.JSON(), nullable=False, server_default="[]"), sa.Column("model_version", sa.String(160)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("run_id", "layer_name", name="uq_agri_fusion_run_layer"))
    op.create_index("ix_agri_fusion_run", "agriculture_fusion_results", ["run_id"]); op.create_index("ix_agri_fusion_status", "agriculture_fusion_results", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agri_fusion_status", table_name="agriculture_fusion_results"); op.drop_index("ix_agri_fusion_run", table_name="agriculture_fusion_results"); op.drop_table("agriculture_fusion_results")
    op.drop_index("ix_agri_sensor_reading_time", table_name="agriculture_sensor_readings"); op.drop_index("ix_agri_sensor_reading_type", table_name="agriculture_sensor_readings"); op.drop_index("ix_agri_sensor_reading_flight", table_name="agriculture_sensor_readings"); op.drop_table("agriculture_sensor_readings")
    for name in ("ix_agri_spectral_quality", "ix_agri_spectral_alignment", "ix_agri_spectral_calibration", "ix_agri_spectral_media", "ix_agri_spectral_flight"): op.drop_index(name, table_name="agriculture_spectral_bands")
    op.drop_table("agriculture_spectral_bands")
    op.drop_index("ix_agri_sensor_calibration_serial", table_name="agriculture_sensor_calibrations"); op.drop_index("ix_agri_sensor_calibration_org", table_name="agriculture_sensor_calibrations"); op.drop_table("agriculture_sensor_calibrations")
