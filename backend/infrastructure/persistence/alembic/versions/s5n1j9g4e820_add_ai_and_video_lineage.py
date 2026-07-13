"""Add AI/video lineage fields used by Phase 3 observability."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s5n1j9g4e820"
down_revision: Union[str, Sequence[str], None] = "r4m0i8f3d719"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_analysis_jobs",
        sa.Column("model_version", sa.String(length=160), nullable=False, server_default="unknown"),
    )
    op.alter_column("video_analysis_jobs", "model_version", server_default=None)


def downgrade() -> None:
    op.drop_column("video_analysis_jobs", "model_version")
