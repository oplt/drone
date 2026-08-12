"""Add the P0 safe Agriculture/Vision/Video workflow contracts.

Revision ID: d7e8f9g0h1i2
Revises: c6f7g8h9i0j1
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e8f9g0h1i2"
down_revision: str | Sequence[str] | None = "c6f7g8h9i0j1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agriculture_analysis_stages",
        sa.Column("execution_key", sa.String(200), nullable=True),
    )
    op.create_index(
        "uq_agri_stage_execution_key",
        "agriculture_analysis_stages",
        ["execution_key"],
        unique=True,
        postgresql_where=sa.text("execution_key IS NOT NULL"),
    )
    op.drop_constraint(
        "ck_vision_training_status", "vision_training_runs", type_="check"
    )
    op.create_check_constraint(
        "ck_vision_training_status",
        "vision_training_runs",
        "status IN ('queued', 'running', 'cancelling', 'completed', 'failed', 'cancelled')",
    )
    op.add_column(
        "vision_projects",
        sa.Column(
            "capability_id",
            sa.String(64),
            nullable=False,
            server_default="object_detection",
        ),
    )
    op.create_index(
        "ix_vision_projects_capability_id",
        "vision_projects",
        ["capability_id"],
    )
    op.alter_column("vision_projects", "capability_id", server_default=None)

    op.add_column(
        "vision_dataset_images",
        sa.Column(
            "annotation_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_vision_image_annotation_revision_nonnegative",
        "vision_dataset_images",
        "annotation_revision >= 0",
    )
    op.alter_column("vision_dataset_images", "annotation_revision", server_default=None)

    op.add_column(
        "video_analysis_jobs",
        sa.Column("orchestration_key", sa.String(160), nullable=True),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("frames_decoded", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("frames_attempted", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("frames_persisted", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("terminal_reason_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("terminal_stage", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_video_analysis_jobs_orchestration_key",
        "video_analysis_jobs",
        ["orchestration_key"],
        unique=True,
    )
    op.create_index(
        "ix_video_analysis_jobs_lease_expires_at",
        "video_analysis_jobs",
        ["lease_expires_at"],
    )
    op.create_check_constraint(
        "ck_video_analysis_job_attempt_nonnegative",
        "video_analysis_jobs",
        "attempt >= 0",
    )
    op.alter_column("video_analysis_jobs", "attempt", server_default=None)
    op.alter_column("video_analysis_jobs", "frames_decoded", server_default=None)
    op.alter_column("video_analysis_jobs", "frames_attempted", server_default=None)
    op.alter_column("video_analysis_jobs", "frames_persisted", server_default=None)

    op.create_table(
        "agriculture_capability_releases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scope_key", sa.String(80), nullable=False),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("capability_id", sa.String(64), nullable=False),
        sa.Column(
            "vision_model_version_id",
            sa.String(36),
            sa.ForeignKey("vision_model_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("sensor_type", sa.String(32), nullable=False, server_default="rgb"),
        sa.Column("crop_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column(
            "inference_profile",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "thresholds",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_agri_capability_release_status",
        ),
    )
    for name, columns in (
        ("ix_agriculture_capability_releases_scope_key", ["scope_key"]),
        ("ix_agriculture_capability_releases_org_id", ["org_id"]),
        ("ix_agriculture_capability_releases_created_by_user_id", ["created_by_user_id"]),
        ("ix_agriculture_capability_releases_capability_id", ["capability_id"]),
        ("ix_agriculture_capability_releases_vision_model_version_id", ["vision_model_version_id"]),
        ("ix_agriculture_capability_releases_status", ["status"]),
    ):
        op.create_index(name, "agriculture_capability_releases", columns)
    op.create_index(
        "uq_agri_active_capability_release",
        "agriculture_capability_releases",
        ["scope_key", "capability_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # Existing production Vision models become the active generic detection release.
    # If a scope has several models, retain the newest model version deterministically.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    mv.id AS version_id,
                    vp.org_id,
                    vp.created_by_user_id,
                    CASE
                        WHEN vp.org_id IS NOT NULL THEN 'org:' || vp.org_id::text
                        ELSE 'user:' || vp.created_by_user_id::text
                    END AS scope_key,
                    vp.capability_id,
                    vm.crop,
                    row_number() OVER (
                        PARTITION BY
                            CASE
                                WHEN vp.org_id IS NOT NULL THEN 'org:' || vp.org_id::text
                                ELSE 'user:' || vp.created_by_user_id::text
                            END,
                            vp.capability_id
                        ORDER BY mv.created_at DESC, mv.id DESC
                    ) AS rank
                FROM vision_model_versions mv
                JOIN vision_models vm ON vm.id = mv.model_id
                JOIN vision_projects vp ON vp.id = vm.project_id
                WHERE mv.status = 'production'
            )
            INSERT INTO agriculture_capability_releases (
                id, scope_key, org_id, created_by_user_id, capability_id,
                vision_model_version_id, status, sensor_type, crop_types,
                inference_profile, thresholds, approved_by_user_id
            )
            SELECT
                'auto-' || version_id,
                scope_key,
                org_id,
                created_by_user_id,
                capability_id,
                version_id,
                'active',
                'rgb',
                json_build_array(crop),
                '{"frame_stride_seconds": 1.0, "confidence_threshold": 0.35,
                  "small_object_mode": false, "tracking_enabled": false,
                  "tracker_type": "bytetrack"}'::json,
                '{}'::json,
                created_by_user_id
            FROM ranked
            WHERE rank = 1
            """
        )
    )

    op.create_table(
        "agriculture_analysis_video_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("capability_id", sa.String(64), nullable=False),
        sa.Column(
            "capability_release_id",
            sa.String(64),
            sa.ForeignKey("agriculture_capability_releases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.String(36),
            sa.ForeignKey("video_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "video_job_id",
            sa.String(36),
            sa.ForeignKey("video_analysis_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "inference_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "run_id",
            "capability_id",
            "video_id",
            name="uq_agri_analysis_video_capability",
        ),
    )
    for name, columns in (
        ("ix_agriculture_analysis_video_jobs_run_id", ["run_id"]),
        ("ix_agriculture_analysis_video_jobs_capability_id", ["capability_id"]),
        ("ix_agriculture_analysis_video_jobs_capability_release_id", ["capability_release_id"]),
        ("ix_agriculture_analysis_video_jobs_video_id", ["video_id"]),
        ("ix_agriculture_analysis_video_jobs_video_job_id", ["video_job_id"]),
    ):
        op.create_index(name, "agriculture_analysis_video_jobs", columns)

    op.add_column(
        "agriculture_model_versions",
        sa.Column(
            "migration_state",
            sa.String(24),
            nullable=False,
            server_default="legacy_unlinked",
        ),
    )
    op.add_column(
        "agriculture_model_versions",
        sa.Column("linked_capability_release_id", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_agri_legacy_model_capability_release",
        "agriculture_model_versions",
        "agriculture_capability_releases",
        ["linked_capability_release_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agriculture_model_versions_migration_state",
        "agriculture_model_versions",
        ["migration_state"],
    )
    op.create_index(
        "ix_agriculture_model_versions_linked_capability_release_id",
        "agriculture_model_versions",
        ["linked_capability_release_id"],
    )
    op.execute(
        sa.text(
            """
            UPDATE agriculture_model_versions
            SET task = CASE task
                WHEN 'canopy' THEN 'canopy_cover'
                WHEN 'rows' THEN 'row_detection'
                WHEN 'weed' THEN 'weed_detection'
                WHEN 'water' THEN 'standing_water'
                WHEN 'visible_water' THEN 'standing_water'
                ELSE task
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH unambiguous AS (
                SELECT legacy.id AS legacy_id, min(release.id) AS release_id
                FROM agriculture_model_versions legacy
                JOIN vision_model_versions vision
                  ON legacy.artifact_uri = vision.weights_uri
                JOIN agriculture_capability_releases release
                  ON release.vision_model_version_id = vision.id
                GROUP BY legacy.id
                HAVING count(*) = 1
            )
            UPDATE agriculture_model_versions legacy
            SET migration_state = 'linked',
                linked_capability_release_id = unambiguous.release_id
            FROM unambiguous
            WHERE legacy.id = unambiguous.legacy_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE agriculture_model_versions
            SET migration_state = 'quarantined'
            WHERE migration_state <> 'linked'
            """
        )
    )
    # Normalize persisted run inputs once. API boundaries reject these aliases after
    # this migration instead of retaining permanent compatibility branches.
    op.execute(
        sa.text(
            """
            UPDATE agriculture_analysis_runs runs
            SET requested_analyses = normalized.value::json
            FROM (
                SELECT id, jsonb_agg(
                    CASE item.value #>> '{}'
                        WHEN 'canopy' THEN 'canopy_cover'
                        WHEN 'rows' THEN 'row_detection'
                        WHEN 'weed' THEN 'weed_detection'
                        WHEN 'water' THEN 'standing_water'
                        WHEN 'visible_water' THEN 'standing_water'
                        ELSE item.value #>> '{}'
                    END ORDER BY item.ordinality
                ) AS value
                FROM agriculture_analysis_runs,
                     jsonb_array_elements(requested_analyses::jsonb)
                     WITH ORDINALITY AS item(value, ordinality)
                GROUP BY id
            ) normalized
            WHERE runs.id = normalized.id
            """
        )
    )
    op.alter_column("agriculture_model_versions", "migration_state", server_default=None)

    op.add_column(
        "agriculture_observations",
        sa.Column(
            "provenance",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column("agriculture_observations", "provenance", server_default=None)
    op.create_index(
        "idx_agri_observation_run_severity_id",
        "agriculture_observations",
        ["run_id", "severity", "id"],
    )
    op.create_index(
        "idx_agri_observation_run_type_severity_id",
        "agriculture_observations",
        ["run_id", "observation_type", "severity", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "uq_agri_stage_execution_key",
        table_name="agriculture_analysis_stages",
    )
    op.drop_column("agriculture_analysis_stages", "execution_key")
    op.drop_index(
        "idx_agri_observation_run_type_severity_id",
        table_name="agriculture_observations",
    )
    op.drop_index(
        "idx_agri_observation_run_severity_id",
        table_name="agriculture_observations",
    )
    op.drop_column("agriculture_observations", "provenance")

    op.execute(
        sa.text(
            "UPDATE vision_training_runs SET status = 'cancelled' WHERE status = 'cancelling'"
        )
    )
    op.drop_constraint(
        "ck_vision_training_status", "vision_training_runs", type_="check"
    )
    op.create_check_constraint(
        "ck_vision_training_status",
        "vision_training_runs",
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
    )
    op.drop_index(
        "ix_agriculture_model_versions_linked_capability_release_id",
        table_name="agriculture_model_versions",
    )
    op.drop_index(
        "ix_agriculture_model_versions_migration_state",
        table_name="agriculture_model_versions",
    )
    op.drop_constraint(
        "fk_agri_legacy_model_capability_release",
        "agriculture_model_versions",
        type_="foreignkey",
    )
    op.drop_column("agriculture_model_versions", "linked_capability_release_id")
    op.drop_column("agriculture_model_versions", "migration_state")

    for name in (
        "ix_agriculture_analysis_video_jobs_video_job_id",
        "ix_agriculture_analysis_video_jobs_video_id",
        "ix_agriculture_analysis_video_jobs_capability_release_id",
        "ix_agriculture_analysis_video_jobs_capability_id",
        "ix_agriculture_analysis_video_jobs_run_id",
    ):
        op.drop_index(name, table_name="agriculture_analysis_video_jobs")
    op.drop_table("agriculture_analysis_video_jobs")

    op.drop_index(
        "uq_agri_active_capability_release",
        table_name="agriculture_capability_releases",
    )
    for name in (
        "ix_agriculture_capability_releases_status",
        "ix_agriculture_capability_releases_vision_model_version_id",
        "ix_agriculture_capability_releases_capability_id",
        "ix_agriculture_capability_releases_created_by_user_id",
        "ix_agriculture_capability_releases_org_id",
        "ix_agriculture_capability_releases_scope_key",
    ):
        op.drop_index(name, table_name="agriculture_capability_releases")
    op.drop_table("agriculture_capability_releases")

    op.drop_constraint(
        "ck_video_analysis_job_attempt_nonnegative",
        "video_analysis_jobs",
        type_="check",
    )
    op.drop_index("ix_video_analysis_jobs_lease_expires_at", table_name="video_analysis_jobs")
    op.drop_index("ix_video_analysis_jobs_orchestration_key", table_name="video_analysis_jobs")
    for column in (
        "terminal_stage",
        "terminal_reason_code",
        "lease_expires_at",
        "heartbeat_at",
        "attempt",
        "frames_persisted",
        "frames_attempted",
        "frames_decoded",
        "orchestration_key",
    ):
        op.drop_column("video_analysis_jobs", column)

    op.drop_constraint(
        "ck_vision_image_annotation_revision_nonnegative",
        "vision_dataset_images",
        type_="check",
    )
    op.drop_column("vision_dataset_images", "annotation_revision")
    op.drop_index("ix_vision_projects_capability_id", table_name="vision_projects")
    op.drop_column("vision_projects", "capability_id")
