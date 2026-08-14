"""Warehouse layout-candidate routes — request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.core.pagination import Page


class LayoutCandidatePage(Page[dict[str, Any]]):
    grouped: dict[str, Any] | None = None


class CandidateIn(BaseModel):
    entity_kind: str
    identity_key: str = Field(min_length=1, max_length=256)
    geometry: dict
    confidence: float = Field(ge=0, le=1)
    source_sequence: int | None = Field(default=None, ge=0)


class CandidateBatchIn(BaseModel):
    layout_version_id: int | None = None
    candidates: list[CandidateIn] = Field(min_length=1, max_length=2000)


class CandidateReviewIn(BaseModel):
    status: Literal["accepted", "rejected"]


class CandidateBatchReviewIn(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=500)
    status: Literal["accepted", "rejected"]


class CandidatePromoteIn(BaseModel):
    candidate_ids: list[int] | None = Field(default=None, max_length=1000)
    revision: int | None = None


__all__ = [
    "CandidateBatchIn",
    "CandidateBatchReviewIn",
    "CandidateIn",
    "CandidatePromoteIn",
    "CandidateReviewIn",
    "LayoutCandidatePage",
]
