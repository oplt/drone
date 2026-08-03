"""Persist agriculture storage class, artifact version and access lifecycle."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f6o7p8q9r0s1"
down_revision: str | Sequence[str] | None = "f5n6o7p8q9r0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agriculture_media_manifests", sa.Column("storage_class", sa.String(32), nullable=False, server_default="standard"))
    op.add_column("agriculture_media_manifests", sa.Column("artifact_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("agriculture_media_manifests", sa.Column("retention_expires_at", sa.DateTime(timezone=True)))
    op.add_column("agriculture_media_manifests", sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_agriculture_media_manifests_retention_expires_at", "agriculture_media_manifests", ["retention_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agriculture_media_manifests_retention_expires_at", table_name="agriculture_media_manifests")
    op.drop_column("agriculture_media_manifests", "revoked_at")
    op.drop_column("agriculture_media_manifests", "retention_expires_at")
    op.drop_column("agriculture_media_manifests", "artifact_version")
    op.drop_column("agriculture_media_manifests", "storage_class")
