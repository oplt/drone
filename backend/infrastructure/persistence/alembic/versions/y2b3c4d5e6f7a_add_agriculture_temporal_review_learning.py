"""Add agriculture temporal comparison, review and learning foundations."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "y2b3c4d5e6f7a"
down_revision: str | Sequence[str] | None = "x1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json(name: str) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'{}'"))


def upgrade() -> None:
    op.create_table("agriculture_flight_alignments",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("reference_flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"), sa.Column("method", sa.String(64), nullable=False, server_default="field_boundary"), sa.Column("alignment_score", sa.Float(), nullable=False, server_default="0"), sa.Column("overlap_pct", sa.Float(), nullable=False, server_default="0"), _json("transform"), sa.Column("failure_reasons", sa.JSON(), nullable=False, server_default="[]"), _json("metrics"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("current_flight_id", "reference_flight_id", name="uq_agri_alignment_pair"))
    op.create_index("ix_agri_alignment_field", "agriculture_flight_alignments", ["field_id"])
    op.create_index("ix_agri_alignment_current", "agriculture_flight_alignments", ["current_flight_id"])
    op.create_index("ix_agri_alignment_reference", "agriculture_flight_alignments", ["reference_flight_id"])
    op.create_index("ix_agri_alignment_status", "agriculture_flight_alignments", ["status"])

    op.create_table("agriculture_observation_changes",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False), sa.Column("current_flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("reference_flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False), sa.Column("current_observation_id", sa.String(64), sa.ForeignKey("agriculture_observations.id", ondelete="CASCADE")), sa.Column("previous_observation_id", sa.String(64), sa.ForeignKey("agriculture_observations.id", ondelete="SET NULL")), sa.Column("observation_type", sa.String(64), nullable=False), sa.Column("state", sa.String(24), nullable=False), _json("geometry_geojson"), _json("reference_geometry_geojson"), sa.Column("area_m2", sa.Float()), sa.Column("delta_area_m2", sa.Float()), sa.Column("delta_intensity", sa.Float()), sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"), _json("uncertainty"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("current_flight_id", "reference_flight_id", "current_observation_id", "previous_observation_id", name="uq_agri_change_pair"))
    for name, cols in (("ix_agri_change_field", ["field_id"]), ("ix_agri_change_current", ["current_flight_id"]), ("ix_agri_change_reference", ["reference_flight_id"]), ("ix_agri_change_current_observation", ["current_observation_id"]), ("ix_agri_change_previous_observation", ["previous_observation_id"]), ("ix_agri_change_type", ["observation_type"]), ("ix_agri_change_state", ["state"]),): op.create_index(name, "agriculture_observation_changes", cols)

    op.create_table("agriculture_review_audits",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("observation_id", sa.String(64), sa.ForeignKey("agriculture_observations.id", ondelete="CASCADE"), nullable=False), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")), sa.Column("action", sa.String(32), nullable=False), sa.Column("from_state", sa.String(24)), sa.Column("to_state", sa.String(24)), sa.Column("reason", sa.Text()), sa.Column("annotation_version", sa.Integer(), nullable=False, server_default="0"), _json("payload"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_audit_observation", "agriculture_review_audits", ["observation_id"]); op.create_index("ix_agri_audit_actor", "agriculture_review_audits", ["actor_user_id"]); op.create_index("ix_agri_audit_org", "agriculture_review_audits", ["org_id"])

    op.create_table("agriculture_observation_annotations",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("observation_id", sa.String(64), sa.ForeignKey("agriculture_observations.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="draft"), sa.Column("label", sa.String(128), nullable=False), sa.Column("severity", sa.Float(), nullable=False, server_default="0"), _json("geometry_geojson"), sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("notes", sa.Text()), sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("observation_id", "version", name="uq_agri_annotation_version"))
    op.create_index("ix_agri_annotation_observation", "agriculture_observation_annotations", ["observation_id"]); op.create_index("ix_agri_annotation_status", "agriculture_observation_annotations", ["status"])

    op.create_table("agriculture_dataset_exports",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")), sa.Column("dataset_key", sa.String(128), nullable=False), sa.Column("direction", sa.String(16), nullable=False, server_default="export"), sa.Column("status", sa.String(24), nullable=False, server_default="queued"), _json("manifest"), sa.Column("checksum", sa.String(128), nullable=False), sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_dataset_export_org", "agriculture_dataset_exports", ["org_id"]); op.create_index("ix_agri_dataset_export_key", "agriculture_dataset_exports", ["dataset_key"]); op.create_index("ix_agri_dataset_export_status", "agriculture_dataset_exports", ["status"])
    op.create_table("agriculture_dataset_items",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("export_id", sa.String(64), sa.ForeignKey("agriculture_dataset_exports.id", ondelete="CASCADE"), nullable=False), sa.Column("annotation_id", sa.String(64), sa.ForeignKey("agriculture_observation_annotations.id", ondelete="CASCADE"), nullable=False), sa.Column("split", sa.String(16), nullable=False, server_default="train"), _json("payload"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_dataset_item_export", "agriculture_dataset_items", ["export_id"]); op.create_index("ix_agri_dataset_item_annotation", "agriculture_dataset_items", ["annotation_id"])

    op.create_table("agriculture_model_versions",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("task", sa.String(64), nullable=False), sa.Column("version", sa.String(160), nullable=False, unique=True), sa.Column("status", sa.String(24), nullable=False, server_default="candidate"), sa.Column("artifact_uri", sa.Text()), sa.Column("dataset_key", sa.String(128)), _json("config"), _json("metrics"), sa.Column("deployed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_model_task", "agriculture_model_versions", ["task"]); op.create_index("ix_agri_model_status", "agriculture_model_versions", ["status"])
    op.create_table("agriculture_model_quality_reports",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("model_version_id", sa.String(64), sa.ForeignKey("agriculture_model_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("scope", sa.String(64), nullable=False, server_default="all"), _json("metrics"), _json("slices"), _json("drift"), sa.Column("evaluation_checksum", sa.String(128), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_agri_model_report_version", "agriculture_model_quality_reports", ["model_version_id"])


def downgrade() -> None:
    op.drop_index("ix_agri_model_report_version", table_name="agriculture_model_quality_reports"); op.drop_table("agriculture_model_quality_reports")
    op.drop_index("ix_agri_model_status", table_name="agriculture_model_versions"); op.drop_index("ix_agri_model_task", table_name="agriculture_model_versions"); op.drop_table("agriculture_model_versions")
    op.drop_index("ix_agri_dataset_item_annotation", table_name="agriculture_dataset_items"); op.drop_index("ix_agri_dataset_item_export", table_name="agriculture_dataset_items"); op.drop_table("agriculture_dataset_items")
    op.drop_index("ix_agri_dataset_export_status", table_name="agriculture_dataset_exports"); op.drop_index("ix_agri_dataset_export_key", table_name="agriculture_dataset_exports"); op.drop_index("ix_agri_dataset_export_org", table_name="agriculture_dataset_exports"); op.drop_table("agriculture_dataset_exports")
    op.drop_index("ix_agri_annotation_status", table_name="agriculture_observation_annotations"); op.drop_index("ix_agri_annotation_observation", table_name="agriculture_observation_annotations"); op.drop_table("agriculture_observation_annotations")
    op.drop_index("ix_agri_audit_org", table_name="agriculture_review_audits"); op.drop_index("ix_agri_audit_actor", table_name="agriculture_review_audits"); op.drop_index("ix_agri_audit_observation", table_name="agriculture_review_audits"); op.drop_table("agriculture_review_audits")
    for name in ("ix_agri_change_state", "ix_agri_change_type", "ix_agri_change_previous_observation", "ix_agri_change_current_observation", "ix_agri_change_reference", "ix_agri_change_current", "ix_agri_change_field"): op.drop_index(name, table_name="agriculture_observation_changes")
    op.drop_table("agriculture_observation_changes")
    op.drop_index("ix_agri_alignment_status", table_name="agriculture_flight_alignments"); op.drop_index("ix_agri_alignment_reference", table_name="agriculture_flight_alignments"); op.drop_index("ix_agri_alignment_current", table_name="agriculture_flight_alignments"); op.drop_index("ix_agri_alignment_field", table_name="agriculture_flight_alignments"); op.drop_table("agriculture_flight_alignments")
