"""Warehouse live-map bridge — ROS workspace helper."""

from __future__ import annotations

from pathlib import Path

from backend.modules.warehouse.service.runtime_settings import ros2_workspace


def _ros2_workspace() -> Path:
    return ros2_workspace()


__all__ = ["_ros2_workspace"]
