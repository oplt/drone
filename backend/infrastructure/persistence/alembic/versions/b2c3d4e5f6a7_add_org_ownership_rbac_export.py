"""add_org_ownership_rbac_export

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-12

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extend user_role enum with new values
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'org_admin'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ops_manager'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'pilot'")

    # 2. Create organizations table (owner_id FK added later to avoid circular dep)
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_org_name"),
        sa.UniqueConstraint("slug", name="uq_org_slug"),
    )

    # 3. Add org_id column to users (nullable first)
    op.add_column("users", sa.Column("org_id", sa.Integer, nullable=True))
    op.create_index("idx_users_org_id", "users", ["org_id"])

    # 4. Data migration: create default org using the first user
    op.execute(
        """
        INSERT INTO organizations (name, slug, owner_id)
        SELECT 'default', 'default', id FROM users ORDER BY id LIMIT 1
        ON CONFLICT DO NOTHING
    """
    )
    op.execute(
        """
        UPDATE users SET org_id = (SELECT id FROM organizations WHERE slug = 'default')
        WHERE org_id IS NULL
    """
    )

    # 5. Now add FKs (data is consistent)
    op.create_foreign_key(
        "fk_users_org_id", "users", "organizations", ["org_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_org_owner",
        "organizations",
        "users",
        ["owner_id"],
        ["id"],
        use_alter=True,
    )

    # 6. Add org_id to remaining tables
    tables = [
        "flights",
        "mission_runtimes",
        "mapping_jobs",
        "fields",
        "warehouse_maps",
        "operational_alerts",
        "herds",
    ]
    for table in tables:
        op.add_column(table, sa.Column("org_id", sa.Integer, nullable=True))
        op.create_index(f"idx_{table}_org_id", table, ["org_id"])
        op.create_foreign_key(
            f"fk_{table}_org_id",
            table,
            "organizations",
            ["org_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.execute(
            f"UPDATE {table} SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL"
        )

    # 7. auth_audit_logs table
    op.create_table(
        "auth_audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("event", sa.String(64), nullable=False, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_auth_audit_user_time", "auth_audit_logs", ["user_id", "created_at"])

    # 8. export_jobs table
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("flight_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "requested_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("download_url", sa.String(2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("export_jobs")
    op.drop_table("auth_audit_logs")

    tables = [
        "herds",
        "operational_alerts",
        "warehouse_maps",
        "fields",
        "mapping_jobs",
        "mission_runtimes",
        "flights",
    ]
    for table in tables:
        op.drop_constraint(f"fk_{table}_org_id", table, type_="foreignkey")
        op.drop_index(f"idx_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")

    op.drop_constraint("fk_org_owner", "organizations", type_="foreignkey")
    op.drop_constraint("fk_users_org_id", "users", type_="foreignkey")
    op.drop_index("idx_users_org_id", table_name="users")
    op.drop_column("users", "org_id")
    op.drop_table("organizations")
