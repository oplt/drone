"""Add agriculture inspection actions, prescriptions, exports and governance."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5e6f7a8b9c0d"
down_revision: str | Sequence[str] | None = "a4d5e6f7a8b9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json(name: str, default: str = "{}") -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(f"'{default}'"))


def upgrade() -> None:
    op.create_table("agriculture_inspection_actions",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("priority_rank", sa.Integer(), nullable=False, server_default="0"), sa.Column("priority_score", sa.Float(), nullable=False, server_default="0"), sa.Column("severity", sa.Float(), nullable=False, server_default="0"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), sa.Column("area_m2", sa.Float()), sa.Column("issue_type", sa.String(96), nullable=False), _json("geometry_geojson"), _json("waypoint_geojson"), sa.Column("rationale", sa.Text(), nullable=False), _json("route_constraints"), _json("uncertainty"), sa.Column("status", sa.String(24), nullable=False, server_default="draft"), sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("review_note", sa.Text()), sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, cols in (("ix_agri_action_run", ["run_id"]), ("ix_agri_action_flight", ["flight_id"]), ("ix_agri_action_field", ["field_id"]), ("ix_agri_action_status", ["status"])): op.create_index(name, "agriculture_inspection_actions", cols)
    op.create_table("agriculture_agronomy_rules",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")), sa.Column("rule_key", sa.String(128), nullable=False), sa.Column("version", sa.String(64), nullable=False), sa.Column("jurisdiction", sa.String(128), nullable=False), sa.Column("crop_type", sa.String(96)), sa.Column("issue_type", sa.String(96), nullable=False), sa.Column("action_kind", sa.String(32), nullable=False, server_default="inspection_only"), _json("parameters"), sa.Column("regulatory_reference", sa.Text()), sa.Column("status", sa.String(24), nullable=False, server_default="draft"), sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("org_id", "rule_key", "version", name="uq_agri_rule_org_key_version"))
    for name, cols in (("ix_agri_rule_org", ["org_id"]), ("ix_agri_rule_status", ["status"]), ("ix_agri_rule_created_by", ["created_by_user_id"]), ("ix_agri_rule_approved_by", ["approved_by_user_id"])): op.create_index(name, "agriculture_agronomy_rules", cols)
    op.create_table("agriculture_prescription_drafts",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("rule_id", sa.String(64), sa.ForeignKey("agriculture_agronomy_rules.id", ondelete="SET NULL")), sa.Column("status", sa.String(24), nullable=False, server_default="draft"), sa.Column("zones", sa.JSON(), nullable=False, server_default="[]"), sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"), _json("rule_provenance"), _json("model_provenance"), sa.Column("assumptions", sa.JSON(), nullable=False, server_default="[]"), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), _json("uncertainty"), sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("review_note", sa.Text()), sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("run_id", "rule_id", name="uq_agri_prescription_run_rule"))
    for name, cols in (("ix_agri_prescription_run", ["run_id"]), ("ix_agri_prescription_flight", ["flight_id"]), ("ix_agri_prescription_field", ["field_id"]), ("ix_agri_prescription_rule", ["rule_id"]), ("ix_agri_prescription_status", ["status"])): op.create_index(name, "agriculture_prescription_drafts", cols)
    op.create_table("agriculture_export_jobs",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE")), sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE")), sa.Column("artifact_kind", sa.String(32), nullable=False), sa.Column("format", sa.String(16), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="pending"), sa.Column("storage_key", sa.String(1024)), sa.Column("checksum", sa.String(128)), sa.Column("content_type", sa.String(128)), _json("source_manifest"), sa.Column("expires_at", sa.DateTime(timezone=True), index=True), sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, cols in (("ix_agri_export_org", ["org_id"]), ("ix_agri_export_field", ["field_id"]), ("ix_agri_export_flight", ["flight_id"]), ("ix_agri_export_run", ["run_id"]), ("ix_agri_export_status", ["status"]), ("ix_agri_export_requested_by", ["requested_by_user_id"]), ("ix_agri_export_approved_by", ["approved_by_user_id"])): op.create_index(name, "agriculture_export_jobs", cols)
    op.create_table("agriculture_governance_audits",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")), sa.Column("entity_type", sa.String(48), nullable=False), sa.Column("entity_id", sa.String(64), nullable=False), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("action", sa.String(48), nullable=False), sa.Column("from_status", sa.String(24)), sa.Column("to_status", sa.String(24)), sa.Column("reason", sa.Text()), _json("payload"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, cols in (("ix_agri_governance_org", ["org_id"]), ("ix_agri_governance_entity_type", ["entity_type"]), ("ix_agri_governance_entity_id", ["entity_id"]), ("ix_agri_governance_actor", ["actor_user_id"]), ("ix_agri_governance_entity_time", ["entity_type", "entity_id", "created_at"])): op.create_index(name, "agriculture_governance_audits", cols)
    op.create_table("agriculture_export_access_audits",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("export_id", sa.String(64), sa.ForeignKey("agriculture_export_jobs.id", ondelete="CASCADE"), nullable=False), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("action", sa.String(32), nullable=False), _json("metadata_json"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, cols in (("ix_agri_export_access_export", ["export_id"]), ("ix_agri_export_access_actor", ["actor_user_id"])): op.create_index(name, "agriculture_export_access_audits", cols)


def downgrade() -> None:
    for name in ("ix_agri_export_access_actor", "ix_agri_export_access_export"): op.drop_index(name, table_name="agriculture_export_access_audits")
    op.drop_table("agriculture_export_access_audits")
    for name in ("ix_agri_governance_entity_time", "ix_agri_governance_actor", "ix_agri_governance_entity_id", "ix_agri_governance_entity_type", "ix_agri_governance_org"): op.drop_index(name, table_name="agriculture_governance_audits")
    op.drop_table("agriculture_governance_audits")
    for name in ("ix_agri_export_approved_by", "ix_agri_export_requested_by", "ix_agri_export_status", "ix_agri_export_run", "ix_agri_export_flight", "ix_agri_export_field", "ix_agri_export_org"): op.drop_index(name, table_name="agriculture_export_jobs")
    op.drop_table("agriculture_export_jobs")
    for name in ("ix_agri_prescription_status", "ix_agri_prescription_rule", "ix_agri_prescription_field", "ix_agri_prescription_flight", "ix_agri_prescription_run"): op.drop_index(name, table_name="agriculture_prescription_drafts")
    op.drop_table("agriculture_prescription_drafts")
    for name in ("ix_agri_rule_approved_by", "ix_agri_rule_created_by", "ix_agri_rule_status", "ix_agri_rule_org"): op.drop_index(name, table_name="agriculture_agronomy_rules")
    op.drop_table("agriculture_agronomy_rules")
    for name in ("ix_agri_action_status", "ix_agri_action_field", "ix_agri_action_flight", "ix_agri_action_run"): op.drop_index(name, table_name="agriculture_inspection_actions")
    op.drop_table("agriculture_inspection_actions")
