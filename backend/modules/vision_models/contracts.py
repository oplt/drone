from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VisionModelRelease:
    """DTO for model lifecycle facts owned by Vision."""

    version_id: str
    status: str
    model_id: str
    model_name: str
    model_version: int
    model_checksum: str
    dataset_id: str
    crop: str
    classes: tuple[str, ...]
    evaluation_metrics: dict[str, Any]
    capability_id: str
    project_org_id: int | None
    project_created_by_user_id: int
