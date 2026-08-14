from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal, cast

from backend.core.config.runtime import settings
from backend.modules.video_analysis.schemas import (
    AnalyzeVideoRequest,
    VideoInferenceProfile,
)
from backend.modules.vision_models.config import vision_settings

PROFILE_SCHEMA_VERSION = "agriculture-inference-profile.v1"

CAPABILITY_PROFILE_IDS = {
    "object_detection": "general_anomaly",
    "stand_count": "stand_count",
    "weed_detection": "weed_detection",
    "crop_health": "visible_crop_health_anomaly",
    "canopy_cover": "canopy_cover",
    "row_detection": "row_detection",
    "standing_water": "standing_water",
    "fruit_counting": "crop_specific_fruit_counting",
    "ripeness_classification": "crop_specific_ripeness_classification",
}


def _first(source: Mapping[str, Any], *keys: str, default: Any) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return default


def _profile_digest(values: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def resolve_inference_profile(
    capability_id: str,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete, validated profile frozen into an analysis fingerprint."""
    if capability_id not in CAPABILITY_PROFILE_IDS:
        raise ValueError(f"No inference profile is defined for {capability_id}")
    source = dict(overrides or {})
    supplied_capability = source.get("capability_id")
    if supplied_capability is not None and supplied_capability != capability_id:
        raise ValueError("Inference profile capability does not match its release")
    sahi_value = source.get("sahi")
    sahi: Mapping[str, Any] = sahi_value if isinstance(sahi_value, dict) else {}
    supplied_sample_fps = _first(source, "sample_fps", default=None)
    if supplied_sample_fps is None:
        stride = float(_first(source, "frame_stride_seconds", default=1.0))
        if stride <= 0:
            raise ValueError("Frame stride must be greater than zero")
        sample_fps = 1.0 / stride
    else:
        sample_fps = float(supplied_sample_fps)
    values = {
        "profile_id": str(
            _first(
                source,
                "profile_id",
                default=f"agriculture.{CAPABILITY_PROFILE_IDS[capability_id]}.baseline",
            )
        ),
        "profile_version": str(_first(source, "profile_version", default=PROFILE_SCHEMA_VERSION)),
        "capability_id": capability_id,
        "sample_fps": sample_fps,
        "image_size": int(_first(source, "image_size", "imgsz", default=640)),
        "confidence_threshold": float(_first(source, "confidence_threshold", default=0.35)),
        "batch_size": int(
            _first(
                source,
                "batch_size",
                "inference_batch_size",
                default=int(settings.video_analysis_inference_batch_size or 1),
            )
        ),
        "precision_mode": str(_first(source, "precision_mode", default="fp32")),
        "sahi_enabled": bool(
            _first(
                source,
                "sahi_enabled",
                "small_object_mode",
                default=sahi.get("enabled", False),
            )
        ),
        "sahi_slice_height": int(
            _first(
                source,
                "sahi_slice_height",
                default=sahi.get("slice_height", vision_settings.video_sahi_slice_height),
            )
        ),
        "sahi_slice_width": int(
            _first(
                source,
                "sahi_slice_width",
                default=sahi.get("slice_width", vision_settings.video_sahi_slice_width),
            )
        ),
        "sahi_overlap_height_ratio": float(
            _first(
                source,
                "sahi_overlap_height_ratio",
                default=sahi.get(
                    "overlap_height_ratio",
                    vision_settings.video_sahi_overlap_height_ratio,
                ),
            )
        ),
        "sahi_overlap_width_ratio": float(
            _first(
                source,
                "sahi_overlap_width_ratio",
                default=sahi.get(
                    "overlap_width_ratio",
                    vision_settings.video_sahi_overlap_width_ratio,
                ),
            )
        ),
        "sahi_postprocess_match_threshold": float(
            _first(
                source,
                "sahi_postprocess_match_threshold",
                default=sahi.get(
                    "postprocess_match_threshold",
                    vision_settings.video_sahi_postprocess_match_threshold,
                ),
            )
        ),
        "tracking_enabled": bool(
            _first(
                source,
                "tracking_enabled",
                default=capability_id == "fruit_counting",
            )
        ),
        "tracker_type": str(_first(source, "tracker_type", default="bytetrack")),
    }
    values["profile_digest"] = _profile_digest(values)
    return VideoInferenceProfile.model_validate(values).model_dump()


def default_inference_profile(capability_id: str) -> dict[str, Any]:
    """Conservative capability identity with the existing runtime settings."""
    return resolve_inference_profile(capability_id)


def video_request_for_profile(
    *,
    capability_id: str,
    model_version_id: str,
    profile: Mapping[str, Any],
) -> AnalyzeVideoRequest:
    resolved = resolve_inference_profile(capability_id, profile)
    typed = VideoInferenceProfile.model_validate(resolved)
    return AnalyzeVideoRequest(
        model_name="yolo26s.pt",
        model_version_id=model_version_id,
        frame_stride_seconds=1.0 / typed.sample_fps,
        confidence_threshold=typed.confidence_threshold,
        small_object_mode=typed.sahi_enabled,
        tracking_enabled=typed.tracking_enabled,
        tracker_type=cast(Literal["bytetrack"], typed.tracker_type),
        inference_profile=typed,
    )
