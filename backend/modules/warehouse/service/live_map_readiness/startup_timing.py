"""Warehouse live-map readiness — startup timing."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def _note_mapping_startup(mark: str) -> None:
    from backend.modules.warehouse.service.startup_timing_hooks import note_mapping_startup_safe

    note_mapping_startup_safe(mark)

def _active_mapping_startup_timing():
    from backend.modules.warehouse.service.startup_timing_hooks import (
        active_mapping_startup_timing_safe,
    )

    return active_mapping_startup_timing_safe()
