"""Add durable tenant-scoped workflow lifecycle events.

Revision ID: p9q0r1s2t3u4
Revises: o8p9q0r1s2t3
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p9q0r1s2t3u4"
down_revision: str | Sequence[str] | None = "o8p9q0r1s2t3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("domain", sa.String(length=48), nullable=False),
        sa.Column("stream_id", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_events_stream_cursor", "workflow_events", ["domain", "stream_id", "id"]
    )
    op.create_index(
        "ix_workflow_events_scope_cursor", "workflow_events", ["org_id", "user_id", "id"]
    )
    op.create_index(
        "uq_workflow_events_dedupe_key",
        "workflow_events",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
        sqlite_where=sa.text("dedupe_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_events_dedupe_key", table_name="workflow_events")
    op.drop_index("ix_workflow_events_scope_cursor", table_name="workflow_events")
    op.drop_index("ix_workflow_events_stream_cursor", table_name="workflow_events")
    op.drop_table("workflow_events")
