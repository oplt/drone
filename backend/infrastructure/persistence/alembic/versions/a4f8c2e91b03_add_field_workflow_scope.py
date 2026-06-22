"""Add workflow_scope to fields for page-specific saved boundaries."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a4f8c2e91b03"
down_revision = "93c855aeb073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fields",
        sa.Column("workflow_scope", sa.String(length=64), nullable=True),
    )
    op.create_index(op.f("ix_fields_workflow_scope"), "fields", ["workflow_scope"], unique=False)
    op.execute(
        sa.text(
            "UPDATE fields SET workflow_scope = 'field_survey' WHERE workflow_scope IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_fields_workflow_scope"), table_name="fields")
    op.drop_column("fields", "workflow_scope")
