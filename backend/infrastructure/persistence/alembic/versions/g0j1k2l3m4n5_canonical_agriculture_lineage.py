"""Complete canonical agriculture media, telemetry, frame and observation lineage."""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "g0j1k2l3m4n5"
down_revision: str | Sequence[str] | None = "f9i0j1k2l3m4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agriculture_telemetry_samples", sa.Column("camera_trigger", sa.Boolean()))

    op.add_column("agriculture_media_manifests", sa.Column("codec", sa.String(64)))
    op.create_foreign_key(
        "fk_agri_media_calibration",
        "agriculture_media_manifests",
        "agriculture_camera_calibrations",
        ["calibration_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_agri_media_flight_checksum_kind",
        "agriculture_media_manifests",
        ["flight_id", "checksum", "source_kind"],
    )
    op.create_check_constraint(
        "ck_agri_media_source_kind",
        "agriculture_media_manifests",
        "source_kind IN ('rgb_video', 'rgb_stills', 'multispectral', "
        "'multispectral_band', 'thermal', 'orthomosaic')",
    )
    op.create_check_constraint(
        "ck_agri_media_retention",
        "agriculture_media_manifests",
        "retention_status IN ('active', 'archived', 'expired', 'legal_hold', 'deleted')",
    )
    op.create_index(
        "idx_agri_media_flight_capture",
        "agriculture_media_manifests",
        ["flight_id", "capture_start_utc"],
    )

    op.add_column(
        "agriculture_frame_lineage",
        sa.Column(
            "pose_interpolation_status", sa.String(24), nullable=False, server_default="unresolved"
        ),
    )
    op.add_column(
        "agriculture_frame_lineage",
        sa.Column(
            "telemetry_sample_before_id",
            sa.Integer(),
            sa.ForeignKey("agriculture_telemetry_samples.id", ondelete="SET NULL"),
        ),
    )
    op.add_column(
        "agriculture_frame_lineage",
        sa.Column(
            "telemetry_sample_after_id",
            sa.Integer(),
            sa.ForeignKey("agriculture_telemetry_samples.id", ondelete="SET NULL"),
        ),
    )
    op.add_column(
        "agriculture_frame_lineage",
        sa.Column(
            "footprint",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        ),
    )
    op.add_column(
        "agriculture_frame_lineage",
        sa.Column("evidence_artifact_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.execute(
        "UPDATE agriculture_frame_lineage SET footprint = "
        "ST_SetSRID(ST_GeomFromGeoJSON(footprint_geojson::text), 4326) "
        "WHERE footprint_geojson IS NOT NULL AND footprint_geojson <> '{}'::json "
        "AND footprint_geojson->>'type' IN ('Polygon', 'MultiPolygon')"
    )
    op.create_check_constraint(
        "ck_agri_frame_pose_status",
        "agriculture_frame_lineage",
        "pose_interpolation_status IN "
        "('unresolved', 'exact', 'interpolated', 'extrapolated', 'unavailable')",
    )
    op.create_check_constraint(
        "ck_agri_frame_footprint_type",
        "agriculture_frame_lineage",
        "footprint IS NULL OR GeometryType(footprint) IN ('POLYGON', 'MULTIPOLYGON')",
    )
    op.create_index(
        "idx_agri_frame_flight_time", "agriculture_frame_lineage", ["flight_id", "timestamp_utc"]
    )
    op.create_index(
        "ix_agriculture_frame_lineage_footprint",
        "agriculture_frame_lineage",
        ["footprint"],
        postgresql_using="gist",
    )

    for _name, column in (
        (
            "analysis_profile",
            sa.Column("analysis_profile", sa.JSON(), nullable=False, server_default="{}"),
        ),
        (
            "input_manifest",
            sa.Column("input_manifest", sa.JSON(), nullable=False, server_default="{}"),
        ),
        ("parameters", sa.Column("parameters", sa.JSON(), nullable=False, server_default="{}")),
        (
            "baseline_flight_id",
            sa.Column(
                "baseline_flight_id",
                sa.String(64),
                sa.ForeignKey("agriculture_flights.id", ondelete="SET NULL"),
            ),
        ),
        ("retry_count", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")),
        ("audit_json", sa.Column("audit_json", sa.JSON(), nullable=False, server_default="{}")),
        (
            "requested_by_user_id",
            sa.Column(
                "requested_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
            ),
        ),
    ):
        op.add_column("agriculture_analysis_runs", column)
    op.create_index(
        "ix_agriculture_analysis_runs_baseline_flight_id",
        "agriculture_analysis_runs",
        ["baseline_flight_id"],
    )
    op.create_index(
        "ix_agriculture_analysis_runs_requested_by_user_id",
        "agriculture_analysis_runs",
        ["requested_by_user_id"],
    )
    op.create_check_constraint(
        "ck_agri_run_progress", "agriculture_analysis_runs", "progress >= 0 AND progress <= 100"
    )
    op.create_check_constraint(
        "ck_agri_run_retry_count", "agriculture_analysis_runs", "retry_count >= 0"
    )

    op.add_column(
        "agriculture_observations",
        sa.Column(
            "geometry",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        ),
    )
    op.add_column(
        "agriculture_observations",
        sa.Column("zone_kind", sa.String(24), nullable=False, server_default="observation"),
    )
    op.execute(
        "UPDATE agriculture_observations SET geometry = "
        "ST_SetSRID(ST_GeomFromGeoJSON(geometry_geojson::text), 4326) "
        "WHERE geometry_geojson IS NOT NULL AND geometry_geojson <> '{}'::json "
        "AND geometry_geojson->>'type' IN ('Polygon', 'MultiPolygon')"
    )
    op.create_index(
        "ix_agriculture_observations_geometry",
        "agriculture_observations",
        ["geometry"],
        postgresql_using="gist",
    )
    op.create_check_constraint(
        "ck_agri_observation_zone_kind",
        "agriculture_observations",
        "zone_kind IN ('observation', 'management_zone', 'prescription_zone')",
    )
    op.create_check_constraint(
        "ck_agri_observation_geometry_srid",
        "agriculture_observations",
        "geometry IS NULL OR ST_SRID(geometry) = 4326",
    )
    op.create_check_constraint(
        "ck_agri_observation_geometry_type",
        "agriculture_observations",
        "geometry IS NULL OR GeometryType(geometry) IN ('POLYGON', 'MULTIPOLYGON')",
    )
    op.create_check_constraint(
        "ck_agri_observation_area", "agriculture_observations", "area_m2 IS NULL OR area_m2 >= 0"
    )
    op.create_check_constraint(
        "ck_agri_observation_severity",
        "agriculture_observations",
        "severity >= 0 AND severity <= 1",
    )
    op.create_check_constraint(
        "ck_agri_observation_confidence",
        "agriculture_observations",
        "confidence >= 0 AND confidence <= 1",
    )

    for table in ("anomaly_zones", "inspection_points"):
        op.add_column(
            table,
            sa.Column(
                "canonical_observation_id",
                sa.String(64),
                sa.ForeignKey("agriculture_observations.id", ondelete="SET NULL"),
            ),
        )
        op.create_index(f"ix_{table}_canonical_observation_id", table, ["canonical_observation_id"])


def downgrade() -> None:
    for table in ("inspection_points", "anomaly_zones"):
        op.drop_index(f"ix_{table}_canonical_observation_id", table_name=table)
        op.drop_column(table, "canonical_observation_id")
    for constraint in (
        "ck_agri_observation_confidence",
        "ck_agri_observation_severity",
        "ck_agri_observation_area",
        "ck_agri_observation_geometry_srid",
        "ck_agri_observation_geometry_type",
        "ck_agri_observation_zone_kind",
    ):
        op.drop_constraint(constraint, "agriculture_observations", type_="check")
    op.drop_index(
        "ix_agriculture_observations_geometry",
        table_name="agriculture_observations",
        postgresql_using="gist",
    )
    op.drop_column("agriculture_observations", "zone_kind")
    op.drop_column("agriculture_observations", "geometry")
    op.drop_constraint("ck_agri_run_retry_count", "agriculture_analysis_runs", type_="check")
    op.drop_constraint("ck_agri_run_progress", "agriculture_analysis_runs", type_="check")
    op.drop_index(
        "ix_agriculture_analysis_runs_requested_by_user_id",
        table_name="agriculture_analysis_runs",
    )
    op.drop_index(
        "ix_agriculture_analysis_runs_baseline_flight_id", table_name="agriculture_analysis_runs"
    )
    for column in (
        "requested_by_user_id",
        "audit_json",
        "retry_count",
        "baseline_flight_id",
        "parameters",
        "input_manifest",
        "analysis_profile",
    ):
        op.drop_column("agriculture_analysis_runs", column)
    op.drop_index(
        "ix_agriculture_frame_lineage_footprint",
        table_name="agriculture_frame_lineage",
        postgresql_using="gist",
    )
    op.drop_index("idx_agri_frame_flight_time", table_name="agriculture_frame_lineage")
    op.drop_constraint("ck_agri_frame_footprint_type", "agriculture_frame_lineage", type_="check")
    op.drop_constraint("ck_agri_frame_pose_status", "agriculture_frame_lineage", type_="check")
    for column in (
        "evidence_artifact_ids",
        "footprint",
        "telemetry_sample_after_id",
        "telemetry_sample_before_id",
        "pose_interpolation_status",
    ):
        op.drop_column("agriculture_frame_lineage", column)
    op.drop_index("idx_agri_media_flight_capture", table_name="agriculture_media_manifests")
    op.drop_constraint("ck_agri_media_retention", "agriculture_media_manifests", type_="check")
    op.drop_constraint("ck_agri_media_source_kind", "agriculture_media_manifests", type_="check")
    op.drop_constraint(
        "uq_agri_media_flight_checksum_kind", "agriculture_media_manifests", type_="unique"
    )
    op.drop_constraint(
        "fk_agri_media_calibration", "agriculture_media_manifests", type_="foreignkey"
    )
    op.drop_column("agriculture_media_manifests", "codec")
    op.drop_column("agriculture_telemetry_samples", "camera_trigger")
