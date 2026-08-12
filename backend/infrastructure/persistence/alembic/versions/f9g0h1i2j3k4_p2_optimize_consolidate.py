"""Add P2 immutable video model provenance.

Revision ID: f9g0h1i2j3k4
Revises: e8f9g0h1i2j3
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9g0h1i2j3k4"
down_revision: str | Sequence[str] | None = "e8f9g0h1i2j3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_analysis_jobs",
        sa.Column("loaded_model_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("video_analysis_jobs", "loaded_model_hash")
