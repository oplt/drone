"""Warehouse layout-candidate routes — public package API."""

from __future__ import annotations

from .helpers import _apply_candidate_metadata
from .router import router

__all__ = ["_apply_candidate_metadata", "router"]

from . import (  # noqa: E402,F401
    candidate_routes,
    displacement_routes,
    promote_routes,
)
