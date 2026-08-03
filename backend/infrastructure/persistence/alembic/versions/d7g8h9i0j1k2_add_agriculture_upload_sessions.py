"""Add durable resumable agriculture media upload sessions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7g8h9i0j1k2"
down_revision: str | Sequence[str] | None = "c6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agriculture_upload_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("temporary_key", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(255)),
        sa.Column("content_type", sa.String(128)),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("received_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(24), nullable=False, server_default="uploading"),
        sa.Column("media_id", sa.String(64), sa.ForeignKey("agriculture_media_manifests.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agri_upload_flight", "agriculture_upload_sessions", ["flight_id"])
    op.create_index("ix_agri_upload_org", "agriculture_upload_sessions", ["org_id"])
    op.create_index("ix_agri_upload_status", "agriculture_upload_sessions", ["status"])
    op.create_index("ix_agri_upload_expires", "agriculture_upload_sessions", ["expires_at"])
    op.create_index("idx_agri_upload_flight_status", "agriculture_upload_sessions", ["flight_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_agri_upload_flight_status", table_name="agriculture_upload_sessions")
    op.drop_index("ix_agri_upload_expires", table_name="agriculture_upload_sessions")
    op.drop_index("ix_agri_upload_status", table_name="agriculture_upload_sessions")
    op.drop_index("ix_agri_upload_org", table_name="agriculture_upload_sessions")
    op.drop_index("ix_agri_upload_flight", table_name="agriculture_upload_sessions")
    op.drop_table("agriculture_upload_sessions")
