"""property patrol mission

Revision ID: 20260611_property_patrol
Revises: e918526bd28a
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260611_property_patrol"
down_revision: str | Sequence[str] | None = "e918526bd28a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "property_patrol_sites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("property_boundary", sa.JSON(), nullable=False),
        sa.Column("flight_safe_area", sa.JSON(), nullable=False),
        sa.Column("no_fly_zones", sa.JSON(), nullable=False),
        sa.Column("privacy_zones", sa.JSON(), nullable=False),
        sa.Column("emergency_landing_zones", sa.JSON(), nullable=False),
        sa.Column("default_home_position", sa.JSON(), nullable=True),
        sa.Column("default_altitude_m", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_property_patrol_sites_name"), "property_patrol_sites", ["name"], unique=False)
    op.create_index(op.f("ix_property_patrol_sites_org_id"), "property_patrol_sites", ["org_id"], unique=False)
    op.create_index(op.f("ix_property_patrol_sites_owner_id"), "property_patrol_sites", ["owner_id"], unique=False)

    op.create_table(
        "property_patrol_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("patrol_mode", sa.String(length=24), nullable=False),
        sa.Column("altitude_m", sa.Float(), nullable=False),
        sa.Column("speed_mps", sa.Float(), nullable=False),
        sa.Column("boundary_offset_m", sa.Float(), nullable=False),
        sa.Column("grid_spacing_m", sa.Float(), nullable=False),
        sa.Column("overlap_percent", sa.Float(), nullable=False),
        sa.Column("camera_direction", sa.String(length=24), nullable=False),
        sa.Column("camera_gimbal_pitch_deg", sa.Float(), nullable=False),
        sa.Column("schedule_interval_minutes", sa.Integer(), nullable=True),
        sa.Column("max_mission_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("min_battery_return_percent", sa.Float(), nullable=False),
        sa.Column("trigger_behavior", sa.String(length=24), nullable=False),
        sa.Column("ai_detection_enabled", sa.Boolean(), nullable=False),
        sa.Column("llm_summary_enabled", sa.Boolean(), nullable=False),
        sa.Column("privacy_blur_faces", sa.Boolean(), nullable=False),
        sa.Column("privacy_blur_license_plates", sa.Boolean(), nullable=False),
        sa.Column("event_clip_recording_only", sa.Boolean(), nullable=False),
        sa.Column("retention_hours_or_days", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["property_patrol_sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_property_patrol_templates_site_id"), "property_patrol_templates", ["site_id"], unique=False)

    op.create_table(
        "property_patrol_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("mission_type", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("route_waypoints", sa.JSON(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drone_id", sa.String(length=128), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["property_patrol_sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["property_patrol_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_property_patrol_runs_operator_id"), "property_patrol_runs", ["operator_id"], unique=False)
    op.create_index(op.f("ix_property_patrol_runs_site_id"), "property_patrol_runs", ["site_id"], unique=False)
    op.create_index(op.f("ix_property_patrol_runs_state"), "property_patrol_runs", ["state"], unique=False)
    op.create_index(op.f("ix_property_patrol_runs_template_id"), "property_patrol_runs", ["template_id"], unique=False)

    op.create_table(
        "property_patrol_sensor_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_event_id", sa.String(length=160), nullable=False),
        sa.Column("sensor_id", sa.String(length=160), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("zone_id", sa.String(length=160), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approx_location", sa.JSON(), nullable=True),
        sa.Column("evidence_clip_id", sa.String(length=255), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["property_patrol_sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "external_event_id", name="uq_property_patrol_event_site_external"),
    )
    op.create_index(op.f("ix_property_patrol_sensor_events_event_type"), "property_patrol_sensor_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_property_patrol_sensor_events_sensor_id"), "property_patrol_sensor_events", ["sensor_id"], unique=False)
    op.create_index(op.f("ix_property_patrol_sensor_events_site_id"), "property_patrol_sensor_events", ["site_id"], unique=False)
    op.create_index(op.f("ix_property_patrol_sensor_events_status"), "property_patrol_sensor_events", ["status"], unique=False)
    op.create_index(op.f("ix_property_patrol_sensor_events_timestamp"), "property_patrol_sensor_events", ["timestamp"], unique=False)
    op.create_index(op.f("ix_property_patrol_sensor_events_zone_id"), "property_patrol_sensor_events", ["zone_id"], unique=False)

    op.create_table(
        "property_patrol_incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("mission_run_id", sa.Integer(), nullable=True),
        sa.Column("sensor_event_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("zone_id", sa.String(length=160), nullable=True),
        sa.Column("detected_objects", sa.JSON(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.JSON(), nullable=True),
        sa.Column("video_clip_id", sa.String(length=255), nullable=True),
        sa.Column("snapshot_ids", sa.JSON(), nullable=False),
        sa.Column("llm_summary", sa.Text(), nullable=True),
        sa.Column("operator_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["mission_run_id"], ["property_patrol_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sensor_event_id"], ["property_patrol_sensor_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["property_patrol_sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_property_patrol_incident_site_status", "property_patrol_incidents", ["site_id", "status"], unique=False)
    op.create_index(op.f("ix_property_patrol_incidents_event_type"), "property_patrol_incidents", ["event_type"], unique=False)
    op.create_index(op.f("ix_property_patrol_incidents_mission_run_id"), "property_patrol_incidents", ["mission_run_id"], unique=False)
    op.create_index(op.f("ix_property_patrol_incidents_sensor_event_id"), "property_patrol_incidents", ["sensor_event_id"], unique=False)
    op.create_index(op.f("ix_property_patrol_incidents_site_id"), "property_patrol_incidents", ["site_id"], unique=False)
    op.create_index(op.f("ix_property_patrol_incidents_source"), "property_patrol_incidents", ["source"], unique=False)
    op.create_index(op.f("ix_property_patrol_incidents_status"), "property_patrol_incidents", ["status"], unique=False)
    op.create_index(op.f("ix_property_patrol_incidents_zone_id"), "property_patrol_incidents", ["zone_id"], unique=False)


def downgrade() -> None:
    op.drop_table("property_patrol_incidents")
    op.drop_table("property_patrol_sensor_events")
    op.drop_table("property_patrol_runs")
    op.drop_table("property_patrol_templates")
    op.drop_table("property_patrol_sites")
