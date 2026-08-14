"""Warehouse coordinate-frame routes — monkeypatchable dependencies."""

from __future__ import annotations

from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.service.coordinate_audit import emit_coordinate_audit
from backend.modules.warehouse.service.coordinate_diagnostics import build_coordinate_diagnostics
from backend.modules.warehouse.service.coordinate_frames import validate_transform
from backend.modules.warehouse.service.drift_guard import (
    ensure_no_active_missions_for_frame_change,
    transform_checksum,
    validate_localization_evidence,
)
from backend.modules.warehouse.service.frame_contract import frame_contract_payload
from backend.modules.warehouse.service.localization_tf_sync import sync_locked_coordinate_frame_to_ros

__all__ = [
    "build_coordinate_diagnostics",
    "emit_coordinate_audit",
    "ensure_no_active_missions_for_frame_change",
    "frame_contract_payload",
    "get_map_or_404",
    "sync_locked_coordinate_frame_to_ros",
    "transform_checksum",
    "validate_localization_evidence",
    "validate_transform",
]
