"""Warehouse layout routes — shared API router."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["warehouse-layouts"])

__all__ = ["router"]
