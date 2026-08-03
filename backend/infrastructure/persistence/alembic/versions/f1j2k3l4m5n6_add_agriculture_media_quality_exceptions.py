"""Persist agriculture post-flight media reconciliation exceptions."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f1j2k3l4m5n6"
down_revision: str | Sequence[str] | None = "f0j1k2l3m4n5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agriculture_media_quality_exceptions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_id", sa.String(64), sa.ForeignKey("agriculture_media_manifests.id", ondelete="CASCADE")),
        sa.Column("upload_id", sa.String(64), sa.ForeignKey("agriculture_upload_sessions.id", ondelete="CASCADE")),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="error"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("flight_id", "media_id", "upload_id", "code", "status", name="uq_agri_media_exception_open"),
    )
    op.create_index("idx_agri_media_exception_flight_status", "agriculture_media_quality_exceptions", ["flight_id", "status"])
    op.create_index("ix_agriculture_media_quality_exceptions_media_id", "agriculture_media_quality_exceptions", ["media_id"])
    op.create_index("ix_agriculture_media_quality_exceptions_upload_id", "agriculture_media_quality_exceptions", ["upload_id"])
    op.create_index("ix_agriculture_media_quality_exceptions_code", "agriculture_media_quality_exceptions", ["code"])
    op.create_index("ix_agriculture_media_quality_exceptions_status", "agriculture_media_quality_exceptions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agriculture_media_quality_exceptions_status", table_name="agriculture_media_quality_exceptions")
    op.drop_index("ix_agriculture_media_quality_exceptions_code", table_name="agriculture_media_quality_exceptions")
    op.drop_index("ix_agriculture_media_quality_exceptions_upload_id", table_name="agriculture_media_quality_exceptions")
    op.drop_index("ix_agriculture_media_quality_exceptions_media_id", table_name="agriculture_media_quality_exceptions")
    op.drop_index("idx_agri_media_exception_flight_status", table_name="agriculture_media_quality_exceptions")
    op.drop_table("agriculture_media_quality_exceptions")
