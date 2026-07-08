"""Strengthen inspection target generation metadata.

Revision ID: p2k8f3g6b145
Revises: o1j7e2f5a934
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p2k8f3g6b145"
down_revision: Union[str, Sequence[str], None] = "o1j7e2f5a934"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "warehouse_scan_targets",
        sa.Column("scanner_metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "warehouse_scan_targets",
        sa.Column("path_validation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("warehouse_scan_targets", sa.Column("failure_reason", sa.String(255)))
    op.alter_column("warehouse_scan_targets", "scanner_metadata_json", server_default=None)
    op.alter_column("warehouse_scan_targets", "path_validation_json", server_default=None)


def downgrade() -> None:
    op.drop_column("warehouse_scan_targets", "failure_reason")
    op.drop_column("warehouse_scan_targets", "path_validation_json")
    op.drop_column("warehouse_scan_targets", "scanner_metadata_json")
