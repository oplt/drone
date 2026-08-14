"""Warehouse scan-target routes — shared API router."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["warehouse"])

__all__ = ["router"]
