"""Warehouse layout-candidate routes — shared API router."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["warehouse-layout-candidates"])

__all__ = ["router"]
