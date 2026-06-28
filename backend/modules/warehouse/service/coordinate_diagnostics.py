from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseCoordinateFrame,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseShelf,
)
from backend.modules.warehouse.service.coordinate_audit import transform_age_ms
from backend.modules.warehouse.service.drift_guard import validate_localization_evidence
from backend.modules.warehouse.service.frame_contract import frame_contract_payload
from backend.modules.warehouse.service.live_map_readiness import probe_mapping_tf_degraded
from backend.modules.warehouse.service.provisional_mapping import (
    block_executable_mission,
    provisional_epoch_snapshot,
)
from backend.modules.warehouse.service.ros_tf_tree_probe import probe_warehouse_ros_tf_tree
from backend.modules.warehouse.service.slam_localization_monitor import slam_localization_snapshot
from backend.modules.warehouse.service.slam_localization_probe import refresh_slam_localization_from_ros

Issue = dict[str, str]


def _issue(code: str, message: str, *, severity: str = "error") -> Issue:
    return {"code": code, "message": message, "severity": severity}


def _frame_summary(row: WarehouseCoordinateFrame | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": int(row.id),
        "version": int(row.version),
        "status": row.status,
        "parent_frame_id": row.parent_frame_id,
        "child_frame_id": row.child_frame_id,
        "confidence": row.confidence,
        "localization_method": row.localization_method,
        "transform_checksum": row.transform_checksum,
        "locked_at": row.locked_at.isoformat() if row.locked_at else None,
        "transform_age_ms": transform_age_ms(row.locked_at),
    }


def _layout_summary(row: WarehouseLayoutVersion | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": int(row.id),
        "version": int(row.version),
        "revision": int(row.revision),
        "status": row.status,
        "coordinate_frame_id": int(row.coordinate_frame_id),
        "provenance_status": row.provenance_status,
        "locked_at": row.locked_at.isoformat() if row.locked_at else None,
    }


async def build_coordinate_diagnostics(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
) -> dict[str, Any]:
    blocking: list[Issue] = []
    warnings: list[Issue] = []

    locked_frame = (
        await db.execute(
            select(WarehouseCoordinateFrame)
            .where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    latest_frame = (
        await db.execute(
            select(WarehouseCoordinateFrame)
            .where(WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id)
            .order_by(WarehouseCoordinateFrame.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    locked_layout = (
        await db.execute(
            select(WarehouseLayoutVersion)
            .where(
                WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id,
                WarehouseLayoutVersion.status == "locked",
            )
            .order_by(WarehouseLayoutVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    latest_layout = (
        await db.execute(
            select(WarehouseLayoutVersion)
            .where(WarehouseLayoutVersion.warehouse_map_id == warehouse_map_id)
            .order_by(WarehouseLayoutVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    localization_evidence: dict[str, Any] | None = None
    if locked_frame is None:
        blocking.append(
            _issue(
                "no_locked_coordinate_frame",
                "No locked warehouse_map coordinate frame; missions are not repeatable.",
            )
        )
    else:
        try:
            localization_evidence = validate_localization_evidence(
                transform=locked_frame.transform_json,
                transform_timestamp=locked_frame.transform_timestamp,
                max_age_s=float(locked_frame.max_age_s),
                covariance=list(locked_frame.covariance_json or []),
                confidence=float(locked_frame.confidence or 0.0),
            )
            if locked_frame.transform_checksum != localization_evidence["checksum_sha256"]:
                blocking.append(
                    _issue(
                        "coordinate_frame_checksum_mismatch",
                        "Locked coordinate frame checksum does not match transform payload.",
                    )
                )
        except ValueError as exc:
            blocking.append(
                _issue("localization_evidence_invalid", str(exc)),
            )

        if locked_layout is not None and int(locked_layout.coordinate_frame_id) != int(
            locked_frame.id
        ):
            blocking.append(
                _issue(
                    "layout_frame_mismatch",
                    "Locked layout version references a different coordinate frame revision.",
                )
            )

    if locked_layout is None:
        blocking.append(
            _issue(
                "no_locked_layout_version",
                "No locked layout version; inspection missions cannot be pinned safely.",
            )
        )
    elif latest_layout is not None and latest_layout.status == "draft":
        warnings.append(
            _issue(
                "draft_layout_pending",
                "A newer draft layout exists; publish or discard before relying on locked layout.",
                severity="warning",
            )
        )

    entity_counts: dict[str, int] = {}
    if locked_layout is not None:
        for kind, model in (
            ("aisles", WarehouseAisle),
            ("racks", WarehouseRack),
            ("shelves", WarehouseShelf),
            ("bins", WarehouseBin),
        ):
            count = (
                await db.execute(
                    select(func.count())
                    .select_from(model)
                    .where(model.layout_version_id == locked_layout.id)
                )
            ).scalar_one()
            entity_counts[kind] = int(count or 0)
        if sum(entity_counts.values()) == 0:
            warnings.append(
                _issue(
                    "layout_empty",
                    "Locked layout has no aisle/rack/shelf/bin entities.",
                    severity="warning",
                )
            )

    if latest_frame is not None and latest_frame.status == "draft":
        warnings.append(
            _issue(
                "draft_coordinate_frame_pending",
                "A draft coordinate frame exists that is not locked.",
                severity="warning",
            )
        )

    frame_contract = frame_contract_payload(coordinate_frame=locked_frame)
    mission_ready = not blocking
    slam_probe, ros_map_odom_tf, ros_tf_tree = await asyncio.gather(
        refresh_slam_localization_from_ros(),
        probe_mapping_tf_degraded(
            parent_frame="warehouse_map",
            child_frame="odom",
        ),
        probe_warehouse_ros_tf_tree(),
    )
    if locked_frame is not None and not ros_map_odom_tf.get("tf_ok"):
        warnings.append(
            _issue(
                "ros_map_odom_tf_missing",
                str(ros_map_odom_tf.get("detail") or "warehouse_map->odom TF is not available in ROS"),
                severity="warning",
            )
        )
    if not ros_tf_tree.get("tf_ok"):
        missing = ros_tf_tree.get("missing_edges") or []
        warnings.append(
            _issue(
                "ros_tf_tree_incomplete",
                "ROS TF tree is missing required edges: "
                + (", ".join(str(edge) for edge in missing) if missing else "unknown"),
                severity="warning",
            )
        )

    slam_localization = slam_localization_snapshot()
    provisional_epoch = provisional_epoch_snapshot(warehouse_map_id)
    if locked_frame is not None and block_executable_mission(
        coordinate_frame_status=str(locked_frame.status),
        localization_method=str(locked_frame.localization_method or ""),
    ):
        warnings.append(
            _issue(
                "provisional_coordinates_active",
                "Locked frame uses provisional SLAM localization; executable missions are blocked.",
                severity="warning",
            )
        )
    if not slam_localization.get("healthy"):
        warnings.append(
            _issue(
                "slam_localization_stale",
                "Live SLAM localization is stale or below confidence threshold.",
                severity="warning",
            )
        )

    return {
        "warehouse_map_id": warehouse_map_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "mission_ready": mission_ready,
        "coordinate_frame": _frame_summary(locked_frame),
        "latest_coordinate_frame": _frame_summary(latest_frame),
        "layout_version": _layout_summary(locked_layout),
        "latest_layout_version": _layout_summary(latest_layout),
        "localization_evidence": localization_evidence,
        "entity_counts": entity_counts,
        "frame_contract_checksum": frame_contract.get("checksum_sha256"),
        "ros_map_odom_tf": ros_map_odom_tf,
        "ros_tf_tree": ros_tf_tree,
        "slam_localization_probe": slam_probe,
        "slam_localization": slam_localization,
        "provisional_epoch": provisional_epoch,
        "blocking_issues": blocking,
        "warnings": warnings,
    }
