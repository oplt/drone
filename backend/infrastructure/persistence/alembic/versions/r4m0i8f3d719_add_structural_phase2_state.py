"""Add Phase 2 risk indexes and durable irrigation jobs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r4m0i8f3d719"
down_revision: str | Sequence[str] | None = "q3l9h7m2c608"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_animal_pos_animal_time_id",
        "animal_positions",
        ["animal_id", "created_at", "id"],
    )
    op.create_index(
        "idx_animals_herd_active",
        "animals",
        ["herd_id", "is_active"],
    )
    op.create_table(
        "irrigation_processing_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("input_checksum", sa.String(length=64), nullable=False),
        sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["mission_runtimes.client_flight_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_irrigation_processing_jobs_mission_id", "irrigation_processing_jobs", ["mission_id"]
    )
    op.create_index(
        "ix_irrigation_processing_jobs_org_id", "irrigation_processing_jobs", ["org_id"]
    )
    op.create_index(
        "ix_irrigation_processing_jobs_requested_by_user_id",
        "irrigation_processing_jobs",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_irrigation_processing_jobs_input_checksum",
        "irrigation_processing_jobs",
        ["input_checksum"],
    )
    op.create_index(
        "ix_irrigation_processing_jobs_mission_checksum",
        "irrigation_processing_jobs",
        ["mission_id", "input_checksum"],
    )
    op.create_index(
        "ix_irrigation_processing_jobs_status", "irrigation_processing_jobs", ["status"]
    )
    op.create_index(
        "ix_irrigation_processing_jobs_celery_task_id",
        "irrigation_processing_jobs",
        ["celery_task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_irrigation_processing_jobs_celery_task_id", table_name="irrigation_processing_jobs"
    )
    op.drop_index("ix_irrigation_processing_jobs_status", table_name="irrigation_processing_jobs")
    op.drop_index(
        "ix_irrigation_processing_jobs_requested_by_user_id",
        table_name="irrigation_processing_jobs",
    )
    op.drop_index(
        "ix_irrigation_processing_jobs_mission_checksum", table_name="irrigation_processing_jobs"
    )
    op.drop_index(
        "ix_irrigation_processing_jobs_input_checksum", table_name="irrigation_processing_jobs"
    )
    op.drop_index("ix_irrigation_processing_jobs_org_id", table_name="irrigation_processing_jobs")
    op.drop_index(
        "ix_irrigation_processing_jobs_mission_id", table_name="irrigation_processing_jobs"
    )
    op.drop_table("irrigation_processing_jobs")
    op.drop_index("idx_animals_herd_active", table_name="animals")
    op.drop_index("idx_animal_pos_animal_time_id", table_name="animal_positions")
