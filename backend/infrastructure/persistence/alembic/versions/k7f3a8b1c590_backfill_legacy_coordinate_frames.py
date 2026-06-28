"""Backfill unlocked legacy takeoff-odom coordinate frames.

Revision ID: k7f3a8b1c590
Revises: j6e2f7a0b489
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "k7f3a8b1c590"
down_revision = "j6e2f7a0b489"
branch_labels = None
depends_on = None

SOURCE = "legacy_takeoff_odom"
IDENTITY = {
    "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
}


def _checksum() -> str:
    body = json.dumps(IDENTITY, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    maps = sa.table("warehouse_maps", sa.column("id", sa.Integer()))
    frames = sa.table(
        "warehouse_coordinate_frames",
        sa.column("warehouse_map_id", sa.Integer()),
        sa.column("version", sa.Integer()),
        sa.column("parent_frame_id", sa.String()),
        sa.column("child_frame_id", sa.String()),
        sa.column("units", sa.String()),
        sa.column("axis_convention", sa.String()),
        sa.column("handedness", sa.String()),
        sa.column("transform_json", sa.JSON()),
        sa.column("covariance_json", sa.JSON()),
        sa.column("source", sa.String()),
        sa.column("localization_method", sa.String()),
        sa.column("transform_timestamp", sa.DateTime(timezone=True)),
        sa.column("max_age_s", sa.Float()),
        sa.column("transform_checksum", sa.String()),
        sa.column("status", sa.String()),
        sa.column("confidence", sa.Float()),
    )
    existing = set(bind.execute(sa.select(frames.c.warehouse_map_id)).scalars())
    now = datetime.now(UTC)
    rows = [
        {
            "warehouse_map_id": map_id,
            "version": 1,
            "parent_frame_id": "warehouse_map",
            "child_frame_id": "odom",
            "units": "m",
            "axis_convention": "ENU",
            "handedness": "right",
            "transform_json": IDENTITY,
            "covariance_json": [],
            "source": SOURCE,
            "localization_method": SOURCE,
            "transform_timestamp": now,
            "max_age_s": 300.0,
            "transform_checksum": _checksum(),
            "status": "draft",
            "confidence": 0.0,
        }
        for map_id in bind.execute(sa.select(maps.c.id)).scalars()
        if map_id not in existing
    ]
    if rows:
        bind.execute(frames.insert(), rows)


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM warehouse_coordinate_frames WHERE source = :source AND status = 'draft'"
        ).bindparams(source=SOURCE)
    )
