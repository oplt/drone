"""Add agriculture flight, profile, telemetry and media lineage foundations."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "w9d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "v8c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agriculture_field_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("crop_type", sa.String(96)), sa.Column("variety", sa.String(128)),
        sa.Column("season", sa.String(64)), sa.Column("planting_date", sa.String(32)),
        sa.Column("growth_stage", sa.String(64)), sa.Column("row_direction_deg", sa.Float()),
        sa.Column("expected_row_spacing_m", sa.Float()), sa.Column("soil_type", sa.String(96)),
        sa.Column("irrigation_method", sa.String(96)), sa.Column("management_zone", sa.String(96)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("notes", sa.Text()), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("field_id", name="uq_agri_profile_field"),
    )
    op.create_index("ix_agriculture_field_profiles_field_id", "agriculture_field_profiles", ["field_id"])
    op.create_index("ix_agriculture_field_profiles_org_id", "agriculture_field_profiles", ["org_id"])
    op.create_index("ix_agriculture_field_profiles_season", "agriculture_field_profiles", ["season"])

    op.create_table(
        "agriculture_camera_calibrations",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("camera_serial", sa.String(128), nullable=False),
        sa.Column("calibration_type", sa.String(32), nullable=False, server_default="rgb"),
        sa.Column("intrinsics_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("distortion_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("extrinsics_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agri_calibration_org_id", "agriculture_camera_calibrations", ["org_id"])
    op.create_index("ix_agri_calibration_camera_serial", "agriculture_camera_calibrations", ["camera_serial"])

    op.create_table(
        "agriculture_flights",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("mission_id", sa.String(64), sa.ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("season", sa.String(64)), sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("quality_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("coverage_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("input_manifest", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("mission_id", name="uq_agri_flight_mission"),
    )
    op.create_index("ix_agriculture_flights_mission_id", "agriculture_flights", ["mission_id"])
    op.create_index("ix_agriculture_flights_field_id", "agriculture_flights", ["field_id"])
    op.create_index("ix_agriculture_flights_org_id", "agriculture_flights", ["org_id"])
    op.create_index("ix_agriculture_flights_season", "agriculture_flights", ["season"])
    op.create_index("ix_agriculture_flights_status", "agriculture_flights", ["status"])
    op.create_index("idx_agri_flights_field_status", "agriculture_flights", ["field_id", "status"])
    op.create_index("idx_agri_flights_org_created", "agriculture_flights", ["org_id", "created_at"])

    op.create_table(
        "agriculture_telemetry_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False), sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("relative_altitude_m", sa.Float()), sa.Column("absolute_altitude_m", sa.Float()),
        sa.Column("roll_deg", sa.Float()), sa.Column("pitch_deg", sa.Float()), sa.Column("yaw_deg", sa.Float()),
        sa.Column("gimbal_roll_deg", sa.Float()), sa.Column("gimbal_pitch_deg", sa.Float()), sa.Column("gimbal_yaw_deg", sa.Float()),
        sa.Column("ground_speed_mps", sa.Float()), sa.Column("gps_quality", sa.Float()),
        sa.Column("source", sa.String(64), nullable=False, server_default="runtime"),
        sa.Column("source_key", sa.String(160)), sa.Column("raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("flight_id", "timestamp_utc", "source", name="uq_agri_telem_flight_time_source"),
    )
    op.create_index("ix_agriculture_telemetry_samples_flight_id", "agriculture_telemetry_samples", ["flight_id"])
    op.create_index("ix_agriculture_telemetry_samples_timestamp_utc", "agriculture_telemetry_samples", ["timestamp_utc"])
    op.create_index("idx_agri_telem_flight_time", "agriculture_telemetry_samples", ["flight_id", "timestamp_utc"])

    op.create_table(
        "agriculture_media_manifests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False), sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False), sa.Column("content_type", sa.String(128)),
        sa.Column("byte_size", sa.Integer()), sa.Column("width", sa.Integer()), sa.Column("height", sa.Integer()),
        sa.Column("duration_seconds", sa.Float()), sa.Column("camera_serial", sa.String(128)), sa.Column("calibration_id", sa.String(128)),
        sa.Column("capture_start_utc", sa.DateTime(timezone=True)), sa.Column("capture_end_utc", sa.DateTime(timezone=True)),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"), sa.Column("retention_status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agriculture_media_manifests_flight_id", "agriculture_media_manifests", ["flight_id"])

    op.create_table(
        "agriculture_frame_lineage",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(64), sa.ForeignKey("agriculture_media_manifests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False), sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("image_width", sa.Integer()), sa.Column("image_height", sa.Integer()),
        sa.Column("source_checksum", sa.String(128)), sa.Column("sampling_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("georef_status", sa.String(24), nullable=False, server_default="unresolved"), sa.Column("georef_error_m", sa.Float()), sa.Column("gsd_cm", sa.Float()),
        sa.Column("footprint_geojson", sa.JSON(), nullable=False, server_default="{}"), sa.Column("quality_metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("media_id", "frame_index", name="uq_agri_frame_media_index"),
    )
    op.create_index("ix_agriculture_frame_lineage_flight_id", "agriculture_frame_lineage", ["flight_id"])
    op.create_index("ix_agriculture_frame_lineage_media_id", "agriculture_frame_lineage", ["media_id"])
    op.create_index("ix_agriculture_frame_lineage_timestamp_utc", "agriculture_frame_lineage", ["timestamp_utc"])

    op.create_table(
        "agriculture_analysis_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("requested_analyses", sa.JSON(), nullable=False, server_default="[]"), sa.Column("model_versions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("calibration_versions", sa.JSON(), nullable=False, server_default="{}"), sa.Column("input_checksum", sa.String(128)),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"), sa.Column("counters", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("quality_gate", sa.JSON(), nullable=False, server_default="{}"), sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("flight_id", "idempotency_key", name="uq_agri_run_flight_idempotency"),
    )
    op.create_index("ix_agriculture_analysis_runs_flight_id", "agriculture_analysis_runs", ["flight_id"])
    op.create_index("ix_agriculture_analysis_runs_status", "agriculture_analysis_runs", ["status"])
    op.create_index("ix_agriculture_analysis_runs_input_checksum", "agriculture_analysis_runs", ["input_checksum"])

def downgrade() -> None:
    op.drop_table("agriculture_analysis_runs")
    op.drop_table("agriculture_frame_lineage")
    op.drop_table("agriculture_media_manifests")
    op.drop_table("agriculture_telemetry_samples")
    op.drop_table("agriculture_flights")
    op.drop_table("agriculture_field_profiles")
    op.drop_table("agriculture_camera_calibrations")
