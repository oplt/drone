"""p3_platform_growth

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-12

Adds P3 models: MissionTemplate, ScheduledRun, ApiKey, WebhookEndpoint,
WebhookDelivery, FieldDeliverable, ComplianceRecord, OperatorCertification,
DeviceReadiness.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Mission Templates ----
    op.create_table(
        "mission_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("mission_type", sa.String(64), nullable=False),
        sa.Column("config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("preflight_profile", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("schedule_cron", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "slug", name="uq_mission_template_org_slug"),
    )
    op.create_index("idx_mission_template_org_active", "mission_templates", ["org_id", "is_active"])
    op.create_index("idx_mission_template_org_id", "mission_templates", ["org_id"])
    op.create_index("idx_mission_template_mission_type", "mission_templates", ["mission_type"])

    # ---- Scheduled Runs ----
    op.create_table(
        "scheduled_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("mission_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("triggered_by", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_scheduled_run_template_time", "scheduled_runs", ["template_id", "created_at"]
    )
    op.create_index("idx_scheduled_run_status", "scheduled_runs", ["status"])

    # ---- API Keys ----
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(8), unique=True, nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes", sa.JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_by_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_api_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("idx_api_key_org_revoked", "api_keys", ["org_id", "revoked"])

    # ---- Webhook Endpoints ----
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("events", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_webhook_endpoint_org_active", "webhook_endpoints", ["org_id", "is_active"])

    # ---- Webhook Deliveries ----
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "endpoint_id",
            sa.Integer,
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_code", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_webhook_delivery_endpoint_time", "webhook_deliveries", ["endpoint_id", "created_at"]
    )
    op.create_index(
        "idx_webhook_delivery_status_retry", "webhook_deliveries", ["status", "next_retry_at"]
    )

    # ---- Field Deliverables ----
    op.create_table(
        "field_deliverables",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "field_id", sa.Integer, sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("share_token", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("idx_field_deliverable_field_type", "field_deliverables", ["field_id", "type"])
    op.create_index("idx_field_deliverable_share_token", "field_deliverables", ["share_token"])

    # ---- Compliance Records ----
    op.create_table(
        "compliance_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "mission_runtime_id",
            sa.Integer,
            sa.ForeignKey("mission_runtimes.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("remote_id_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("laanc_auth_number", sa.String(64), nullable=True),
        sa.Column("laanc_auth_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preflight_ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
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
    )
    op.create_index("idx_compliance_record_org", "compliance_records", ["org_id"])
    op.create_index("idx_compliance_record_mission", "compliance_records", ["mission_runtime_id"])

    # ---- Operator Certifications ----
    op.create_table(
        "operator_certifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cert_type", sa.String(64), nullable=False),
        sa.Column("cert_number", sa.String(128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issuing_authority", sa.String(255), nullable=True),
        sa.Column("document_url", sa.String(2048), nullable=True),
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
    )
    op.create_index(
        "idx_operator_cert_user_type", "operator_certifications", ["user_id", "cert_type"]
    )
    op.create_index("idx_operator_cert_org", "operator_certifications", ["org_id"])

    # ---- Device Readiness ----
    op.create_table(
        "device_readiness",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("device_name", sa.String(255), nullable=False),
        sa.Column("last_inspection_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_inspection_due", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="airworthy"),
        sa.Column("notes", sa.Text, nullable=True),
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
        sa.UniqueConstraint("device_id", "org_id", name="uq_device_readiness_device_org"),
    )
    op.create_index("idx_device_readiness_org_status", "device_readiness", ["org_id", "status"])
    op.create_index("idx_device_readiness_device_id", "device_readiness", ["device_id"])


def downgrade() -> None:
    op.drop_table("device_readiness")
    op.drop_table("operator_certifications")
    op.drop_table("compliance_records")
    op.drop_table("field_deliverables")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_table("api_keys")
    op.drop_table("scheduled_runs")
    op.drop_table("mission_templates")
