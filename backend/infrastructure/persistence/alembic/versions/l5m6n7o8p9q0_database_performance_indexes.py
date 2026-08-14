"""Database performance: telemetry receipts and FK join indexes.

Revision ID: l5m6n7o8p9q0
Revises: k4l5m6n7o8p9
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l5m6n7o8p9q0"
down_revision: str | Sequence[str] | None = "k4l5m6n7o8p9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agriculture_telemetry_receipts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "flight_id",
            sa.String(length=64),
            sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("payload_checksum", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "flight_id",
            "idempotency_key",
            name="uq_agri_telemetry_receipt_flight_key",
        ),
    )
    op.create_index(
        "ix_agriculture_telemetry_receipts_flight_id",
        "agriculture_telemetry_receipts",
        ["flight_id"],
        unique=False,
    )

    op.create_index(
        "ix_agri_media_manifests_calibration_id",
        "agriculture_media_manifests",
        ["calibration_id"],
        unique=False,
    )
    op.create_index(
        "ix_agri_upload_sessions_media_id",
        "agriculture_upload_sessions",
        ["media_id"],
        unique=False,
    )
    op.create_index(
        "ix_agri_frame_lineage_telemetry_before_id",
        "agriculture_frame_lineage",
        ["telemetry_sample_before_id"],
        unique=False,
    )
    op.create_index(
        "ix_agri_frame_lineage_telemetry_after_id",
        "agriculture_frame_lineage",
        ["telemetry_sample_after_id"],
        unique=False,
    )
    op.create_index(
        "ix_vision_annotations_created_by_user_id",
        "vision_annotations",
        ["created_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vision_annotations_created_by_user_id", table_name="vision_annotations")
    op.drop_index(
        "ix_agri_frame_lineage_telemetry_after_id",
        table_name="agriculture_frame_lineage",
    )
    op.drop_index(
        "ix_agri_frame_lineage_telemetry_before_id",
        table_name="agriculture_frame_lineage",
    )
    op.drop_index("ix_agri_upload_sessions_media_id", table_name="agriculture_upload_sessions")
    op.drop_index(
        "ix_agri_media_manifests_calibration_id",
        table_name="agriculture_media_manifests",
    )
    op.drop_index(
        "ix_agriculture_telemetry_receipts_flight_id",
        table_name="agriculture_telemetry_receipts",
    )
    op.drop_table("agriculture_telemetry_receipts")
