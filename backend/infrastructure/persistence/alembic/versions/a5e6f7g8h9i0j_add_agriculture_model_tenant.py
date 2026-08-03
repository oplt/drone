"""Tenant-scope agriculture model registry records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5e6f7g8h9i0j"
down_revision: str | Sequence[str] | None = "z3c4d5e6f7a8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agriculture_model_versions", sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")))
    op.create_index("ix_agriculture_model_versions_org_id", "agriculture_model_versions", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_agriculture_model_versions_org_id", table_name="agriculture_model_versions")
    op.drop_column("agriculture_model_versions", "org_id")
