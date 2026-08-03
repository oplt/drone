"""Persist agriculture media security/quarantine state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6f7g8h9i0j1"
down_revision: str | Sequence[str] | None = "a5e6f7g8h9i0j"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agriculture_media_manifests", sa.Column("security_status", sa.String(24), nullable=False, server_default="passed"))
    op.add_column("agriculture_media_manifests", sa.Column("security_reason", sa.String(512)))
    op.add_column("agriculture_media_manifests", sa.Column("security_checked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_agri_media_security_status", "agriculture_media_manifests", ["security_status"])
    op.create_check_constraint("ck_agri_media_security", "agriculture_media_manifests", "security_status IN ('pending', 'passed', 'quarantined', 'rejected')")


def downgrade() -> None:
    op.drop_constraint("ck_agri_media_security", "agriculture_media_manifests", type_="check")
    op.drop_index("ix_agri_media_security_status", table_name="agriculture_media_manifests")
    op.drop_column("agriculture_media_manifests", "security_checked_at")
    op.drop_column("agriculture_media_manifests", "security_reason")
    op.drop_column("agriculture_media_manifests", "security_status")
