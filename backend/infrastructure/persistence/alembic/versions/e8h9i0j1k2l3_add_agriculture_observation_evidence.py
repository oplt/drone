"""Add canonical agriculture observation source links."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8h9i0j1k2l3"
down_revision: str | Sequence[str] | None = "d7g8h9i0j1k2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agriculture_observation_evidence",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("observation_id", sa.String(64), sa.ForeignKey("agriculture_observations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("detection_id", sa.String(36), sa.ForeignKey("video_detections.id", ondelete="SET NULL")),
        sa.Column("frame_lineage_id", sa.String(64), sa.ForeignKey("agriculture_frame_lineage.id", ondelete="SET NULL")),
        sa.Column("media_id", sa.String(64), sa.ForeignKey("agriculture_media_manifests.id", ondelete="SET NULL")),
        sa.Column("source_video_id", sa.String(36), sa.ForeignKey("video_assets.id", ondelete="SET NULL")),
        sa.Column("evidence_path", sa.Text()),
        sa.Column("frame_index", sa.Integer()),
        sa.Column("timestamp_seconds", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("observation_id", "detection_id", name="uq_agri_observation_detection"),
    )
    for name, cols in (("ix_agri_obs_evidence_observation", ["observation_id"]), ("ix_agri_obs_evidence_detection", ["detection_id"]), ("ix_agri_obs_evidence_frame", ["frame_lineage_id"]), ("ix_agri_obs_evidence_media", ["media_id"]), ("ix_agri_obs_evidence_video", ["source_video_id"])):
        op.create_index(name, "agriculture_observation_evidence", cols)


def downgrade() -> None:
    for name in ("ix_agri_obs_evidence_video", "ix_agri_obs_evidence_media", "ix_agri_obs_evidence_frame", "ix_agri_obs_evidence_detection", "ix_agri_obs_evidence_observation"):
        op.drop_index(name, table_name="agriculture_observation_evidence")
    op.drop_table("agriculture_observation_evidence")
