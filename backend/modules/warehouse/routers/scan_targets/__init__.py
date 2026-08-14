"""Warehouse scan-target routes — public package API."""

from __future__ import annotations

from .deps import (
    MockWarehouseScanner,
    append_rescan_plan,
    assert_map_or_404,
    block_executable_mission,
    build_inspection_waypoints,
    compute_scan_pose,
    create_mission_revision_pins,
    emit_coordinate_audit,
    get_locked_coordinate_frame,
    get_map_or_404,
    get_scan_target_or_404,
    is_legacy_mission,
    load_locked_layout_bin_index,
    metric_add,
    order_targets,
    persist_inspection_feedback,
    persist_layout_drift_report,
    record_mission_rejection,
    require_legacy_same_origin_confirmation,
    require_warehouse_map_frames,
    resolve_bin_context,
    resolve_bin_context_from_index,
    transform_age_ms,
    validate_slam_localization_for_execution,
    verify_mission_revision_pins,
)
from .helpers import _set_scan_target_cache_headers
from .router import router

__all__ = [
    "MockWarehouseScanner",
    "_set_scan_target_cache_headers",
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
    "router",
    "transform_age_ms",
    "validate_slam_localization_for_execution",
    "verify_mission_revision_pins",
]

from . import import_routes, inspection_mock_routes, inspection_routes, target_routes  # noqa: E402,F401
from .import_routes import import_warehouse_scan_targets  # noqa: E402
from .inspection_mock_routes import run_warehouse_inspection_mission_mock  # noqa: E402
from .inspection_routes import (  # noqa: E402
    approve_warehouse_inspection_mission,
    create_warehouse_inspection_mission,
    get_warehouse_inspection_mission,
    list_warehouse_inspection_results,
)
from .target_routes import (  # noqa: E402
    compute_warehouse_scan_pose,
    create_warehouse_scan_target,
    delete_warehouse_scan_target,
    get_warehouse_scan_target,
    list_warehouse_scan_targets,
    update_warehouse_scan_target,
)

__all__ += [
    "approve_warehouse_inspection_mission",
    "compute_warehouse_scan_pose",
    "create_warehouse_inspection_mission",
    "create_warehouse_scan_target",
    "delete_warehouse_scan_target",
    "get_warehouse_inspection_mission",
    "get_warehouse_scan_target",
    "import_warehouse_scan_targets",
    "list_warehouse_inspection_results",
    "list_warehouse_scan_targets",
    "run_warehouse_inspection_mission_mock",
    "update_warehouse_scan_target",
]
