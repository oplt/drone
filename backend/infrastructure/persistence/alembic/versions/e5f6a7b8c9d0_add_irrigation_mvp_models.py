"""add_irrigation_mvp_models

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-12

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capture_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(64),
            sa.ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Integer,
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("image_uri", sa.String(2048), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("alt_m", sa.Float(), nullable=True),
        sa.Column("yaw_deg", sa.Float(), nullable=True),
        sa.Column("pitch_deg", sa.Float(), nullable=True),
        sa.Column("roll_deg", sa.Float(), nullable=True),
        sa.Column("waypoint_seq", sa.Integer(), nullable=True),
        sa.Column("frame_width", sa.Integer(), nullable=True),
        sa.Column("frame_height", sa.Integer(), nullable=True),
        sa.Column("meta_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_capture_records_mission_id", "capture_records", ["mission_id"])
    op.create_index("ix_capture_records_org_id", "capture_records", ["org_id"])
    op.create_index("ix_capture_records_project_id", "capture_records", ["project_id"])
    op.create_index(
        "idx_capture_records_mission_time",
        "capture_records",
        ["mission_id", "timestamp_utc"],
    )

    op.create_table(
        "processed_field_layers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(64),
            sa.ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Integer,
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("capture_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stitched_image_uri", sa.String(2048), nullable=True),
        sa.Column("footprints_geojson", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("tile_manifest", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("bounds_geojson", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("resolution_m_per_px", sa.Float(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("mission_id", name="uq_processed_field_layers_mission_id"),
    )
    op.create_index(
        "ix_processed_field_layers_mission_id", "processed_field_layers", ["mission_id"]
    )
    op.create_index("ix_processed_field_layers_org_id", "processed_field_layers", ["org_id"])
    op.create_index(
        "ix_processed_field_layers_project_id", "processed_field_layers", ["project_id"]
    )
    op.create_index("ix_processed_field_layers_status", "processed_field_layers", ["status"])

    op.create_table(
        "anomaly_zones",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(64),
            sa.ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "layer_id",
            sa.Integer,
            sa.ForeignKey("processed_field_layers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Integer,
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("area_m2", sa.Float(), nullable=True),
        sa.Column("centroid_lat", sa.Float(), nullable=False),
        sa.Column("centroid_lon", sa.Float(), nullable=False),
        sa.Column("polygon_geojson", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence_image_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("meta_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_anomaly_zones_mission_id", "anomaly_zones", ["mission_id"])
    op.create_index("ix_anomaly_zones_layer_id", "anomaly_zones", ["layer_id"])
    op.create_index("ix_anomaly_zones_org_id", "anomaly_zones", ["org_id"])
    op.create_index("ix_anomaly_zones_project_id", "anomaly_zones", ["project_id"])
    op.create_index("ix_anomaly_zones_type", "anomaly_zones", ["type"])
    op.create_index("idx_anomaly_zones_mission_type", "anomaly_zones", ["mission_id", "type"])

    op.create_table(
        "inspection_points",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(64),
            sa.ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "zone_id",
            sa.Integer,
            sa.ForeignKey("anomaly_zones.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Integer,
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("meta_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_inspection_points_mission_id", "inspection_points", ["mission_id"])
    op.create_index("ix_inspection_points_zone_id", "inspection_points", ["zone_id"])
    op.create_index("ix_inspection_points_org_id", "inspection_points", ["org_id"])
    op.create_index("ix_inspection_points_project_id", "inspection_points", ["project_id"])
    op.create_index(
        "idx_inspection_points_mission_priority",
        "inspection_points",
        ["mission_id", "priority"],
    )


def downgrade() -> None:
    op.drop_index("idx_inspection_points_mission_priority", table_name="inspection_points")
    op.drop_index("ix_inspection_points_project_id", table_name="inspection_points")
    op.drop_index("ix_inspection_points_org_id", table_name="inspection_points")
    op.drop_index("ix_inspection_points_zone_id", table_name="inspection_points")
    op.drop_index("ix_inspection_points_mission_id", table_name="inspection_points")
    op.drop_table("inspection_points")

    op.drop_index("idx_anomaly_zones_mission_type", table_name="anomaly_zones")
    op.drop_index("ix_anomaly_zones_type", table_name="anomaly_zones")
    op.drop_index("ix_anomaly_zones_project_id", table_name="anomaly_zones")
    op.drop_index("ix_anomaly_zones_org_id", table_name="anomaly_zones")
    op.drop_index("ix_anomaly_zones_layer_id", table_name="anomaly_zones")
    op.drop_index("ix_anomaly_zones_mission_id", table_name="anomaly_zones")
    op.drop_table("anomaly_zones")

    op.drop_index("ix_processed_field_layers_status", table_name="processed_field_layers")
    op.drop_index("ix_processed_field_layers_project_id", table_name="processed_field_layers")
    op.drop_index("ix_processed_field_layers_org_id", table_name="processed_field_layers")
    op.drop_index("ix_processed_field_layers_mission_id", table_name="processed_field_layers")
    op.drop_table("processed_field_layers")

    op.drop_index("idx_capture_records_mission_time", table_name="capture_records")
    op.drop_index("ix_capture_records_project_id", table_name="capture_records")
    op.drop_index("ix_capture_records_org_id", table_name="capture_records")
    op.drop_index("ix_capture_records_mission_id", table_name="capture_records")
    op.drop_table("capture_records")
