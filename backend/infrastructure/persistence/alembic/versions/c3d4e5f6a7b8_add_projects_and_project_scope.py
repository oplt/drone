"""add_projects_and_project_scope

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-12

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "slug", name="uq_project_org_slug"),
    )
    op.create_index("idx_projects_org_id", "projects", ["org_id"])
    op.create_index("idx_projects_created_by_user_id", "projects", ["created_by_user_id"])

    op.execute(
        """
        INSERT INTO projects (org_id, name, slug, created_by_user_id, is_default)
        SELECT
            organizations.id,
            'Default Project',
            'default',
            organizations.owner_id,
            TRUE
        FROM organizations
        """
    )

    scoped_tables = [
        "flights",
        "fields",
        "mapping_jobs",
        "warehouse_maps",
        "mission_runtimes",
        "export_jobs",
    ]
    for table in scoped_tables:
        op.add_column(table, sa.Column("project_id", sa.Integer, nullable=True))
        op.create_index(f"idx_{table}_project_id", table, ["project_id"])
        op.create_foreign_key(
            f"fk_{table}_project_id",
            table,
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.execute(
            f"""
            UPDATE {table}
            SET project_id = projects.id
            FROM projects
            WHERE {table}.org_id = projects.org_id
              AND projects.slug = 'default'
              AND {table}.project_id IS NULL
            """
        )


def downgrade() -> None:
    scoped_tables = [
        "export_jobs",
        "mission_runtimes",
        "warehouse_maps",
        "mapping_jobs",
        "fields",
        "flights",
    ]
    for table in scoped_tables:
        op.drop_constraint(f"fk_{table}_project_id", table, type_="foreignkey")
        op.drop_index(f"idx_{table}_project_id", table_name=table)
        op.drop_column(table, "project_id")

    op.drop_index("idx_projects_created_by_user_id", table_name="projects")
    op.drop_index("idx_projects_org_id", table_name="projects")
    op.drop_table("projects")
