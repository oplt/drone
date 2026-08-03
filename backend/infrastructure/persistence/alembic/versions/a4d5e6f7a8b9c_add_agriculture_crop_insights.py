"""Add agriculture crop-risk, growth, harvest-label and yield records."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4d5e6f7a8b9c"
down_revision: str | Sequence[str] | None = "z3c4d5e6f7a8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json(name: str, default: str = "{}") -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(f"'{default}'"))


def upgrade() -> None:
    op.create_table("agriculture_crop_risks",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("issue_type", sa.String(96), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="candidate"), sa.Column("crop_type", sa.String(96)), sa.Column("growth_stage", sa.String(64)), _json("geometry_geojson"), sa.Column("severity", sa.Float(), nullable=False, server_default="0"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), sa.Column("trend", sa.String(24), nullable=False, server_default="unknown"), _json("uncertainty"), sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"), _json("sensor_values"), sa.Column("inspection_points", sa.JSON(), nullable=False, server_default="[]"), _json("factors"), _json("applicability"), sa.Column("model_version", sa.String(160)), sa.Column("review_state", sa.String(24), nullable=False, server_default="unreviewed"), sa.Column("review_note", sa.Text()), sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_crop_risk_run", "agriculture_crop_risks", ["run_id"]); op.create_index("ix_agri_crop_risk_flight", "agriculture_crop_risks", ["flight_id"]); op.create_index("ix_agri_crop_risk_field", "agriculture_crop_risks", ["field_id"]); op.create_index("ix_agri_crop_risk_issue", "agriculture_crop_risks", ["issue_type"]); op.create_index("ix_agri_crop_risk_status", "agriculture_crop_risks", ["status"]); op.create_index("ix_agri_crop_risk_review", "agriculture_crop_risks", ["review_state"])
    op.create_table("agriculture_growth_metrics",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("metric_kind", sa.String(32), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="not_measured"), sa.Column("units", sa.String(32)), _json("summary"), sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("source_timestamps", sa.JSON(), nullable=False, server_default="[]"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), _json("uncertainty"), sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("model_version", sa.String(160)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("run_id", "metric_kind", name="uq_agri_growth_metric_run_kind"))
    op.create_index("ix_agri_growth_metric_run", "agriculture_growth_metrics", ["run_id"]); op.create_index("ix_agri_growth_metric_flight", "agriculture_growth_metrics", ["flight_id"]); op.create_index("ix_agri_growth_metric_field", "agriculture_growth_metrics", ["field_id"]); op.create_index("ix_agri_growth_metric_status", "agriculture_growth_metrics", ["status"])
    op.create_table("agriculture_growth_stage_estimates",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="not_measured"), sa.Column("predicted_stage", sa.String(64)), sa.Column("candidates", sa.JSON(), nullable=False, server_default="[]"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), _json("inputs"), sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"), _json("uncertainty"), sa.Column("human_stage", sa.String(64)), sa.Column("correction_note", sa.Text()), sa.Column("corrected_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("corrected_at", sa.DateTime(timezone=True)), sa.Column("model_version", sa.String(160)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("run_id", name="uq_agri_stage_estimate_run"))
    op.create_index("ix_agri_stage_estimate_run", "agriculture_growth_stage_estimates", ["run_id"]); op.create_index("ix_agri_stage_estimate_field", "agriculture_growth_stage_estimates", ["field_id"])
    op.create_table("agriculture_harvest_labels",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")), sa.Column("harvest_date", sa.DateTime(timezone=True), nullable=False), sa.Column("crop_type", sa.String(96), nullable=False), sa.Column("variety", sa.String(128)), sa.Column("yield_value", sa.Float(), nullable=False), sa.Column("yield_unit", sa.String(32), nullable=False), sa.Column("area_ha", sa.Float()), sa.Column("source", sa.String(128), nullable=False), sa.Column("quality", sa.Float(), nullable=False, server_default="0"), _json("metadata_json"), sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_harvest_label_field", "agriculture_harvest_labels", ["field_id"]); op.create_index("ix_agri_harvest_label_org", "agriculture_harvest_labels", ["org_id"]); op.create_index("ix_agri_harvest_label_date", "agriculture_harvest_labels", ["harvest_date"])
    op.create_table("agriculture_yield_forecasts",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="not_applicable"), sa.Column("units", sa.String(32)), _json("forecast_range"), _json("confidence_interval"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), _json("factors"), _json("applicability"), sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("harvest_label_ids", sa.JSON(), nullable=False, server_default="[]"), _json("uncertainty"), sa.Column("model_version", sa.String(160)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("run_id", name="uq_agri_yield_forecast_run"))
    op.create_index("ix_agri_yield_forecast_run", "agriculture_yield_forecasts", ["run_id"]); op.create_index("ix_agri_yield_forecast_flight", "agriculture_yield_forecasts", ["flight_id"]); op.create_index("ix_agri_yield_forecast_field", "agriculture_yield_forecasts", ["field_id"]); op.create_index("ix_agri_yield_forecast_status", "agriculture_yield_forecasts", ["status"])


def downgrade() -> None:
    for name, table in (("ix_agri_yield_forecast_status", "agriculture_yield_forecasts"), ("ix_agri_yield_forecast_field", "agriculture_yield_forecasts"), ("ix_agri_yield_forecast_flight", "agriculture_yield_forecasts"), ("ix_agri_yield_forecast_run", "agriculture_yield_forecasts")):
        op.drop_index(name, table_name=table)
    op.drop_table("agriculture_yield_forecasts")
    for name in ("ix_agri_harvest_label_date", "ix_agri_harvest_label_org", "ix_agri_harvest_label_field"):
        op.drop_index(name, table_name="agriculture_harvest_labels")
    op.drop_table("agriculture_harvest_labels")
    for name in ("ix_agri_stage_estimate_field", "ix_agri_stage_estimate_run"):
        op.drop_index(name, table_name="agriculture_growth_stage_estimates")
    op.drop_table("agriculture_growth_stage_estimates")
    for name in ("ix_agri_growth_metric_status", "ix_agri_growth_metric_field", "ix_agri_growth_metric_flight", "ix_agri_growth_metric_run"):
        op.drop_index(name, table_name="agriculture_growth_metrics")
    op.drop_table("agriculture_growth_metrics")
    for name in ("ix_agri_crop_risk_review", "ix_agri_crop_risk_status", "ix_agri_crop_risk_issue", "ix_agri_crop_risk_field", "ix_agri_crop_risk_flight", "ix_agri_crop_risk_run"):
        op.drop_index(name, table_name="agriculture_crop_risks")
    op.drop_table("agriculture_crop_risks")
