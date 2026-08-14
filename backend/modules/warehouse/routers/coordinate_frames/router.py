"""Warehouse coordinate-frame routes — shared API router."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["warehouse-coordinate-frames"])

__all__ = ["router"]
