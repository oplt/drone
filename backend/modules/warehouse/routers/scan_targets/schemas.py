"""Warehouse scan-target routes — local request schemas."""

from __future__ import annotations

from pydantic import BaseModel


class InspectionMissionApprovalIn(BaseModel):
    approved: bool


__all__ = ["InspectionMissionApprovalIn"]
