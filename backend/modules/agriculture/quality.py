"""Deterministic image and telemetry quality gates for agriculture inference."""

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Iterable

import cv2
import numpy as np


@dataclass(frozen=True)
class FrameQualityResult:
    metrics: dict[str, float]
    score: float
    state: str
    reasons: tuple[str, ...]


def compute_frame_quality(image_bgr: np.ndarray, *, previous_bgr: np.ndarray | None = None, hooks: Iterable[Callable[[np.ndarray], dict[str, Any]]] = ()) -> FrameQualityResult:
    if image_bgr is None or image_bgr.size == 0:
        return FrameQualityResult({}, 0.0, "blocked", ("empty_frame",))
    image = image_bgr.astype(np.uint8, copy=False)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    clipped_ratio = float(np.mean(gray >= 250))
    black_ratio = float(np.mean(gray <= 8))
    glare_ratio = float(np.mean((gray >= 235) & (cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1] < 45)))
    contrast = float(np.std(gray))
    smooth = cv2.GaussianBlur(gray, (3, 3), 0)
    noise = float(np.std(gray.astype(np.float32) - smooth.astype(np.float32)))
    duplicate_score = 0.0
    motion_score = 0.0
    if previous_bgr is not None and previous_bgr.shape == image.shape:
        previous_gray = cv2.cvtColor(previous_bgr.astype(np.uint8, copy=False), cv2.COLOR_BGR2GRAY)
        difference = float(np.mean(cv2.absdiff(gray, previous_gray)) / 255.0)
        duplicate_score = max(0.0, 1.0 - difference * 12.0)
        motion_score = min(1.0, difference * 8.0)
    blur_quality = min(1.0, laplacian / 500.0)
    exposure_quality = max(0.0, 1.0 - min(1.0, clipped_ratio * 8.0 + black_ratio * 8.0))
    contrast_quality = min(1.0, contrast / 64.0)
    glare_quality = max(0.0, 1.0 - min(1.0, glare_ratio * 8.0))
    score = max(0.0, min(1.0, 0.35 * blur_quality + 0.25 * exposure_quality + 0.2 * contrast_quality + 0.15 * glare_quality + 0.05 * (1.0 - duplicate_score)))
    reasons: list[str] = []
    if blur_quality < 0.25: reasons.append("blur")
    if exposure_quality < 0.45: reasons.append("exposure")
    if glare_quality < 0.45: reasons.append("glare")
    if duplicate_score > 0.98: reasons.append("duplicate_frame")
    hook_metrics: dict[str, Any] = {}
    for hook in hooks:
        try:
            hook_metrics.update(hook(image) or {})
        except Exception as exc:
            hook_metrics.setdefault("hook_errors", []).append(type(exc).__name__)
    for key, value in hook_metrics.items():
        if key.endswith("_warning") and value: reasons.append(key)
    state = "blocked" if score < 0.35 or "blur" in reasons else "warning" if score < 0.65 or reasons else "pass"
    return FrameQualityResult(
        metrics={"blur_score": blur_quality, "motion_score": motion_score, "clipped_ratio": clipped_ratio, "black_ratio": black_ratio, "glare_ratio": glare_ratio, "contrast_score": contrast_quality, "noise_score": min(1.0, noise / 32.0), "duplicate_score": duplicate_score, "compression_corruption_score": min(1.0, noise / 32.0), **hook_metrics},
        score=score,
        state=state,
        reasons=tuple(reasons),
    )


def telemetry_quality_summary(samples: Iterable[Any]) -> dict[str, Any]:
    rows = sorted(samples, key=lambda row: row.timestamp_utc)
    if not rows:
        return {"status": "blocked", "reason": "telemetry_missing", "sample_count": 0}
    gaps = [
        (right.timestamp_utc - left.timestamp_utc).total_seconds()
        for left, right in zip(rows, rows[1:])
    ]
    altitudes = [float(row.relative_altitude_m or row.absolute_altitude_m) for row in rows if row.relative_altitude_m is not None or row.absolute_altitude_m is not None]
    attitudes = [max(abs(float(row.roll_deg or 0)), abs(float(row.pitch_deg or 0))) for row in rows]
    speeds = [float(row.ground_speed_mps) for row in rows if row.ground_speed_mps is not None]
    gimbal_pitches = [float(row.gimbal_pitch_deg) for row in rows if row.gimbal_pitch_deg is not None]
    gps_quality = [float(row.gps_quality) for row in rows if row.gps_quality is not None]
    headings = [float(row.yaw_deg) for row in rows if row.yaw_deg is not None]
    gap_count = sum(1 for gap in gaps if gap > 5.0)
    status = "blocked" if gap_count and gap_count / max(1, len(rows)) > 0.1 else "warning" if gap_count else "pass"
    heading_change = max((abs(right - left) for left, right in zip(headings, headings[1:])), default=0.0)
    return {"status": status, "sample_count": len(rows), "gap_count": gap_count, "max_gap_s": max(gaps, default=0.0), "altitude_min_m": min(altitudes, default=None), "altitude_max_m": max(altitudes, default=None), "altitude_change_m": (max(altitudes) - min(altitudes)) if altitudes else None, "max_attitude_excursion_deg": max(attitudes, default=0.0), "max_speed_mps": max(speeds, default=None), "gimbal_pitch_min_deg": min(gimbal_pitches, default=None), "gimbal_pitch_max_deg": max(gimbal_pitches, default=None), "gps_quality_min": min(gps_quality, default=None), "max_heading_change_deg": heading_change}


def analysis_suitability(*, estimated_gsd_cm: float | None, target_gsd_cm: float, requested_analyses: Iterable[str]) -> dict[str, Any]:
    if estimated_gsd_cm is None:
        return {"status": "blocked", "reason": "gsd_unresolved", "allowed_analyses": []}
    plant_level = {"stand_count", "gaps", "double_plants", "plant_detection"}
    blocked = sorted(plant_level.intersection(requested_analyses)) if estimated_gsd_cm > target_gsd_cm * 1.5 else []
    return {"status": "blocked" if blocked else "pass", "estimated_gsd_cm": estimated_gsd_cm, "target_gsd_cm": target_gsd_cm, "blocked_analyses": blocked, "allowed_analyses": sorted(set(requested_analyses) - set(blocked))}


def aggregate_quality(results: Iterable[FrameQualityResult]) -> dict[str, Any]:
    rows = list(results)
    if not rows:
        return {"status": "blocked", "score": 0.0, "frame_count": 0, "blocked_frames": 0, "warning_frames": 0, "reasons": ["no_quality_frames"]}
    scores = [row.score for row in rows]
    reasons = sorted({reason for row in rows for reason in row.reasons})
    blocked = sum(row.state == "blocked" for row in rows)
    warnings = sum(row.state == "warning" for row in rows)
    score = float(np.mean(scores))
    return {"status": "blocked" if blocked / len(rows) > 0.2 else "warning" if warnings or blocked else "pass", "score": score, "frame_count": len(rows), "blocked_frames": blocked, "warning_frames": warnings, "reasons": reasons}
