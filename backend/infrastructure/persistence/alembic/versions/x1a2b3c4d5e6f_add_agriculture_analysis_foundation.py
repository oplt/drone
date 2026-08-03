"""Add retryable agriculture analysis stages, quality, observations and baselines."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "x1a2b3c4d5e6f"
down_revision: str | Sequence[str] | None = "w9d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("agriculture_analysis_stages",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_name", sa.String(64), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="queued"), sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"), sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("input_checksum", sa.String(128)), sa.Column("output_checksum", sa.String(128)), sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"), sa.Column("error", sa.Text()), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("run_id", "stage_name", name="uq_agri_stage_run_name"))
    op.create_index("ix_agri_stage_run_id", "agriculture_analysis_stages", ["run_id"])
    op.create_index("ix_agri_stage_status", "agriculture_analysis_stages", ["status"])

    op.create_table("agriculture_frame_quality",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("media_id", sa.String(64), sa.ForeignKey("agriculture_media_manifests.id", ondelete="SET NULL")), sa.Column("frame_index", sa.Integer(), nullable=False), sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False), sa.Column("blur_score", sa.Float()), sa.Column("motion_score", sa.Float()), sa.Column("clipped_ratio", sa.Float()), sa.Column("black_ratio", sa.Float()), sa.Column("glare_ratio", sa.Float()), sa.Column("contrast_score", sa.Float()), sa.Column("noise_score", sa.Float()), sa.Column("duplicate_score", sa.Float()), sa.Column("telemetry_quality", sa.String(24)), sa.Column("score", sa.Float(), nullable=False, server_default="0"), sa.Column("state", sa.String(24), nullable=False, server_default="warning"), sa.Column("evidence_path", sa.Text()), sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("run_id", "frame_index", name="uq_agri_quality_run_frame"))
    op.create_index("ix_agri_quality_run_id", "agriculture_frame_quality", ["run_id"])
    op.create_index("ix_agri_quality_flight_id", "agriculture_frame_quality", ["flight_id"])
    op.create_index("ix_agri_quality_timestamp", "agriculture_frame_quality", ["timestamp_utc"])
    op.create_index("ix_agri_quality_state", "agriculture_frame_quality", ["state"])

    op.create_table("agriculture_observations",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("observation_type", sa.String(64), nullable=False), sa.Column("geometry_geojson", sa.JSON(), nullable=False, server_default="{}"), sa.Column("georef_status", sa.String(24), nullable=False, server_default="unresolved"), sa.Column("area_m2", sa.Float()), sa.Column("severity", sa.Float(), nullable=False, server_default="0"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), sa.Column("uncertainty", sa.JSON(), nullable=False, server_default="{}"), sa.Column("first_detected", sa.DateTime(timezone=True)), sa.Column("last_detected", sa.DateTime(timezone=True)), sa.Column("trend", sa.String(24), nullable=False, server_default="unknown"), sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("sensor_values", sa.JSON(), nullable=False, server_default="{}"), sa.Column("model_version", sa.String(160)), sa.Column("review_state", sa.String(24), nullable=False, server_default="unreviewed"), sa.Column("review_label", sa.String(128)), sa.Column("review_note", sa.Text()), sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, columns in (("ix_agri_observation_run_id", ["run_id"]), ("ix_agri_observation_flight_id", ["flight_id"]), ("ix_agri_observation_field_id", ["field_id"]), ("ix_agri_observation_type", ["observation_type"]), ("ix_agri_observation_severity", ["severity"]), ("ix_agri_observation_confidence", ["confidence"]), ("ix_agri_observation_review_state", ["review_state"]), ("idx_agri_observation_run_type", ["run_id", "observation_type"])): op.create_index(name, "agriculture_observations", columns)

    op.create_table("agriculture_analysis_layers",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("layer_name", sa.String(64), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="ready"), sa.Column("geojson", sa.JSON(), nullable=False, server_default="{}"), sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"), sa.Column("checksum", sa.String(128), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("run_id", "layer_name", name="uq_agri_layer_run_name"))
    op.create_index("ix_agri_layer_run_id", "agriculture_analysis_layers", ["run_id"])

    op.create_table("agriculture_health_baselines",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")), sa.Column("profile_key", sa.String(128), nullable=False), sa.Column("features", sa.JSON(), nullable=False, server_default="{}"), sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0.25"), sa.Column("source_run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="SET NULL")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("field_id", "profile_key", name="uq_agri_baseline_field_profile"))
    op.create_index("ix_agri_baseline_field_id", "agriculture_health_baselines", ["field_id"])
    op.create_index("ix_agri_baseline_org_id", "agriculture_health_baselines", ["org_id"])


def downgrade() -> None:
    op.drop_table("agriculture_health_baselines")
    op.drop_table("agriculture_analysis_layers")
    op.drop_table("agriculture_observations")
    op.drop_table("agriculture_frame_quality")
    op.drop_table("agriculture_analysis_stages")
