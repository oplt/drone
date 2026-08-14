"""Live-map flight manifest — public package API."""

from __future__ import annotations

from .build import build_manifest_from_flight_dir
from .coverage import build_coverage_repair_waypoints, build_rack_face_coverage
from .deps import require_rgb_for_save, warehouse_live_map_chunk_storage
from .models import LiveMapFlightManifest
from .persist import load_flight_manifest, save_flight_manifest
from .validation import (
    finalize_manifest_integrity,
    validate_manifest_chunk_files,
    validate_save_quality,
)

__all__ = [
    "LiveMapFlightManifest",
    "build_coverage_repair_waypoints",
    "build_manifest_from_flight_dir",
    "build_rack_face_coverage",
    "finalize_manifest_integrity",
    "load_flight_manifest",
    "require_rgb_for_save",
    "save_flight_manifest",
    "validate_manifest_chunk_files",
    "validate_save_quality",
    "warehouse_live_map_chunk_storage",
]
