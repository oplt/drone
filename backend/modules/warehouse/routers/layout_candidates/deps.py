"""Warehouse layout-candidate routes — monkeypatchable dependencies."""

from __future__ import annotations

from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.service.coordinate_audit import emit_coordinate_audit
from backend.modules.warehouse.service.layout import bump_revision, parse_revision, require_draft_revision
from backend.modules.warehouse.service.scan_to_layout import (
    CandidateInput,
    candidate_status,
    displacement_m,
    persist_candidates,
    review_reasons,
)

__all__ = [
    "CandidateInput",
    "bump_revision",
    "candidate_status",
    "displacement_m",
    "emit_coordinate_audit",
    "get_map_or_404",
    "parse_revision",
    "persist_candidates",
    "require_draft_revision",
    "review_reasons",
]
