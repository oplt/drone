"""Persist agriculture preflight evaluator and operator sign-off provenance."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "e9i0j1k2l3m4"
down_revision: str | Sequence[str] | None = "d8h9i0j1k2l3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agriculture_preflight_snapshots", sa.Column("evaluator_version", sa.String(64), nullable=False, server_default="agriculture-preflight.v2"))
    op.add_column("agriculture_preflight_snapshots", sa.Column("signoff_hash", sa.String(128)))
    op.add_column("agriculture_preflight_snapshots", sa.Column("operator_notes", sa.Text()))


def downgrade() -> None:
    op.drop_column("agriculture_preflight_snapshots", "operator_notes")
    op.drop_column("agriculture_preflight_snapshots", "signoff_hash")
    op.drop_column("agriculture_preflight_snapshots", "evaluator_version")
