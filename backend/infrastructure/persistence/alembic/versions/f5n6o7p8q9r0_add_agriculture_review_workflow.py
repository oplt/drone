"""Add accountable agriculture review feedback and assignments."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5n6o7p8q9r0"
down_revision: str | Sequence[str] | None = ("f4m5n6o7p8q9", "a1b2c3d4e5f6", "g0j1k2l3m4n5")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agriculture_observations", sa.Column("assigned_to_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("agriculture_observations", sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agriculture_observations_assigned_to_user_id", "agriculture_observations", ["assigned_to_user_id"])
    op.create_index("ix_agriculture_observations_review_due_at", "agriculture_observations", ["review_due_at"])

    op.create_table(
        "agriculture_observation_feedback",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("observation_id", sa.String(64), sa.ForeignKey("agriculture_observations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("feedback_type", sa.String(24), nullable=False, server_default="correction"),
        sa.Column("proposed_label", sa.String(128)),
        sa.Column("proposed_severity", sa.Float()),
        sa.Column("proposed_zone_kind", sa.String(24)),
        sa.Column("proposed_geometry_geojson", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(24), nullable=False, server_default="submitted"),
        sa.Column("decision_note", sa.Text()),
        sa.Column("annotation_id", sa.String(64), sa.ForeignKey("agriculture_observation_annotations.id", ondelete="SET NULL")),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("feedback_type IN ('correction', 'disagreement', 'comment')", name="ck_agri_feedback_type"),
        sa.CheckConstraint("status IN ('submitted', 'accepted', 'rejected')", name="ck_agri_feedback_status"),
        sa.CheckConstraint("proposed_severity IS NULL OR (proposed_severity >= 0 AND proposed_severity <= 1)", name="ck_agri_feedback_severity"),
    )
    for name, column in (("observation_id", "observation_id"), ("actor_user_id", "actor_user_id"), ("org_id", "org_id"), ("status", "status"), ("annotation_id", "annotation_id")):
        op.create_index(f"ix_agri_feedback_{name}", "agriculture_observation_feedback", [column])
    op.add_column("agriculture_dataset_items", sa.Column("feedback_id", sa.String(64), sa.ForeignKey("agriculture_observation_feedback.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_agriculture_dataset_items_feedback_id", "agriculture_dataset_items", ["feedback_id"])

    op.add_column("agriculture_inspection_actions", sa.Column("assigned_to_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("agriculture_inspection_actions", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agriculture_inspection_actions_assigned_to_user_id", "agriculture_inspection_actions", ["assigned_to_user_id"])
    op.create_index("ix_agriculture_inspection_actions_due_at", "agriculture_inspection_actions", ["due_at"])

    op.add_column("operational_alerts", sa.Column("assigned_to_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("operational_alerts", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_operational_alerts_assigned_to_user_id", "operational_alerts", ["assigned_to_user_id"])
    op.create_index("ix_operational_alerts_due_at", "operational_alerts", ["due_at"])


def downgrade() -> None:
    for name in ("ix_operational_alerts_due_at", "ix_operational_alerts_assigned_to_user_id"):
        op.drop_index(name, table_name="operational_alerts")
    op.drop_column("operational_alerts", "due_at")
    op.drop_column("operational_alerts", "assigned_to_user_id")
    for name in ("ix_agriculture_inspection_actions_due_at", "ix_agriculture_inspection_actions_assigned_to_user_id"):
        op.drop_index(name, table_name="agriculture_inspection_actions")
    op.drop_column("agriculture_inspection_actions", "due_at")
    op.drop_column("agriculture_inspection_actions", "assigned_to_user_id")
    for name in ("ix_agri_feedback_annotation_id", "ix_agri_feedback_status", "ix_agri_feedback_org_id", "ix_agri_feedback_actor_user_id", "ix_agri_feedback_observation_id"):
        op.drop_index(name, table_name="agriculture_observation_feedback")
    op.drop_index("ix_agriculture_dataset_items_feedback_id", table_name="agriculture_dataset_items")
    op.drop_column("agriculture_dataset_items", "feedback_id")
    op.drop_table("agriculture_observation_feedback")
    op.drop_index("ix_agriculture_observations_review_due_at", table_name="agriculture_observations")
    op.drop_index("ix_agriculture_observations_assigned_to_user_id", table_name="agriculture_observations")
    op.drop_column("agriculture_observations", "review_due_at")
    op.drop_column("agriculture_observations", "assigned_to_user_id")
