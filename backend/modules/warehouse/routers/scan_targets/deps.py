"""Warehouse scan-target routes — monkeypatchable dependencies."""

from __future__ import annotations

from backend.modules.warehouse.http_access import assert_map_or_404, get_map_or_404
from backend.modules.warehouse.http_helpers import get_scan_target_or_404
from backend.modules.warehouse.service.coordinate_audit import emit_coordinate_audit, transform_age_ms
from backend.modules.warehouse.service.coordinate_frames import (
    get_locked_coordinate_frame,
    require_warehouse_map_frames,
)
from backend.modules.warehouse.service.inspection import (
    MockWarehouseScanner,
    build_inspection_waypoints,
    compute_scan_pose,
    order_targets,
)
from backend.modules.warehouse.service.inspection_feedback import (
    append_rescan_plan,
    persist_inspection_feedback,
    persist_layout_drift_report,
)
from backend.modules.warehouse.service.layout import (
    load_locked_layout_bin_index,
    resolve_bin_context,
    resolve_bin_context_from_index,
)
from backend.modules.warehouse.service.mission_revisions import (
    create_mission_revision_pins,
    is_legacy_mission,
    require_legacy_same_origin_confirmation,
    verify_mission_revision_pins,
)
from backend.modules.warehouse.observability.warehouse_coordinate_metrics import record_mission_rejection
from backend.modules.warehouse.service.provisional_mapping import block_executable_mission
from backend.modules.warehouse.service.slam_localization_monitor import (
    validate_slam_localization_for_execution,
)
from backend.observability.metrics import add as metric_add

__all__ = [
    "MockWarehouseScanner",
    "append_rescan_plan",
    "assert_map_or_404",
    "block_executable_mission",
    "build_inspection_waypoints",
    "compute_scan_pose",
    "create_mission_revision_pins",
    "emit_coordinate_audit",
    "get_locked_coordinate_frame",
    "get_map_or_404",
    "get_scan_target_or_404",
    "is_legacy_mission",
    "load_locked_layout_bin_index",
    "metric_add",
    "order_targets",
    "persist_inspection_feedback",
    "persist_layout_drift_report",
    "record_mission_rejection",
    "require_legacy_same_origin_confirmation",
    "require_warehouse_map_frames",
    "resolve_bin_context",
    "resolve_bin_context_from_index",
    "transform_age_ms",
    "validate_slam_localization_for_execution",
    "verify_mission_revision_pins",
]
