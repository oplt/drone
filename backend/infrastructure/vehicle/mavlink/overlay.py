from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.core.config.runtime import settings
from backend.infrastructure.vehicle.mavlink._client_refs import client_module
from backend.infrastructure.vehicle.mavlink.config import logger


class MavlinkOverlayMixin:
    """Warehouse odometry overlay and home AMSL helpers."""

    def _load_warehouse_odometry_overlay(self) -> dict[str, object]:
        path_raw = (settings.WAREHOUSE_ODOMETRY_STATE_PATH or "").strip()
        if not path_raw:
            return {}
        now = client_module().time.time()
        if now - self._warehouse_odometry_overlay_loaded_at < 0.5:
            return self._warehouse_odometry_overlay
        self._warehouse_odometry_overlay_loaded_at = now
        path = Path(path_raw)
        if not path.exists():
            self._warehouse_odometry_overlay = {}
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed reading warehouse odometry state from %s", path, exc_info=True)
            self._warehouse_odometry_overlay = {}
            return {}
        self._warehouse_odometry_overlay = payload if isinstance(payload, dict) else {}
        return self._warehouse_odometry_overlay

    @staticmethod
    def _overlay_float(overlay: dict[str, object], key: str) -> float | None:
        value = overlay.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _overlay_bool(overlay: dict[str, object], key: str) -> bool | None:
        value = overlay.get(key)
        if isinstance(value, bool):
            return value
        return None

    def get_home_amsl(self) -> float:
        # AMSL in meters (DroneKit global_frame.alt)
        alt = getattr(self.vehicle.location.global_frame, "alt", None)
        if alt is None:
            raise RuntimeError("global_frame.alt not available (AMSL).")
        return float(alt)

