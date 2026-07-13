"""Make warehouse structure extraction lineage first-class on durable jobs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v8c4d5e6f7a8"
down_revision: str | Sequence[str] | None = "u7b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "warehouse_mapping_jobs",
        sa.Column(
            "algorithm_version",
            sa.String(length=128),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "warehouse_mapping_jobs",
        sa.Column("input_checksum", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "warehouse_mapping_jobs",
        sa.Column("extraction_params", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("warehouse_mapping_jobs", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "warehouse_mapping_jobs",
        sa.Column("failure_reason_codes", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index(
        "ix_warehouse_mapping_jobs_algorithm_version",
        "warehouse_mapping_jobs",
        ["algorithm_version"],
    )
    op.create_index(
        "ix_warehouse_mapping_jobs_input_checksum",
        "warehouse_mapping_jobs",
        ["input_checksum"],
    )
    op.alter_column("warehouse_mapping_jobs", "algorithm_version", server_default=None)
    op.alter_column("warehouse_mapping_jobs", "extraction_params", server_default=None)
    op.alter_column("warehouse_mapping_jobs", "failure_reason_codes", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_warehouse_mapping_jobs_input_checksum", table_name="warehouse_mapping_jobs")
    op.drop_index(
        "ix_warehouse_mapping_jobs_algorithm_version", table_name="warehouse_mapping_jobs"
    )
    op.drop_column("warehouse_mapping_jobs", "extraction_params")
    op.drop_column("warehouse_mapping_jobs", "failure_reason_codes")
    op.drop_column("warehouse_mapping_jobs", "confidence")
    op.drop_column("warehouse_mapping_jobs", "input_checksum")
    op.drop_column("warehouse_mapping_jobs", "algorithm_version")
