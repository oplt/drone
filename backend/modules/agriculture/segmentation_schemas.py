"""Research-only segmentation experiment request contracts."""

from typing import Literal

from pydantic import BaseModel, Field


class SegmentationExperimentDatasetIn(BaseModel):
    crop_type: str = Field(..., min_length=1, max_length=96)
    labeled_images: int = Field(..., ge=0)
    annotated_instances: int = Field(..., ge=0)
    independent_fields: int = Field(..., ge=0)
    split: Literal["train", "validation", "test", "shadow", "holdout"]
    source_checksum: str = Field(..., min_length=16, max_length=128)


class SegmentationExperimentMetricsIn(BaseModel):
    weed_zone_iou: float = Field(..., ge=0, le=1)
    area_mae_pct: float = Field(..., ge=0, le=100)


class SegmentationExperimentIn(BaseModel):
    dataset: SegmentationExperimentDatasetIn
    detection_baseline: SegmentationExperimentMetricsIn
    segmentation_candidate: SegmentationExperimentMetricsIn
