"""CPU-safe RGB fallbacks used when a validated agriculture model is unavailable."""

from typing import Any

import cv2
import numpy as np


def segment_rgb_crop_soil_water(image_bgr: np.ndarray) -> dict[str, Any]:
    if image_bgr is None or image_bgr.size == 0:
        return {"status": "blocked", "reason": "empty_frame"}
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([28, 35, 25]), np.array([95, 255, 255])) > 0
    blue_dark = (hsv[:, :, 0] > 85) & (hsv[:, :, 0] < 135) & (hsv[:, :, 1] > 35) & (hsv[:, :, 2] < 220)
    brown = (hsv[:, :, 0] < 28) & (hsv[:, :, 1] > 25) & (hsv[:, :, 2] > 25)
    total = max(1, image_bgr.shape[0] * image_bgr.shape[1])
    return {"status": "pass", "canopy_pct": float(green.mean() * 100), "soil_pct": float(brown.mean() * 100), "visible_water_pct": float(blue_dark.mean() * 100), "unknown_pct": float(max(0.0, 1.0 - float((green | brown | blue_dark).mean())) * 100), "masks": {"crop": green, "soil": brown, "water": blue_dark}}


def infer_row_structure(crop_mask: np.ndarray) -> dict[str, Any]:
    if crop_mask is None or crop_mask.size == 0:
        return {"status": "unresolved", "reason": "missing_canopy_mask"}
    edges = cv2.Canny((crop_mask.astype(np.uint8) * 255), 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(10, crop_mask.shape[1] // 20), minLineLength=max(10, crop_mask.shape[1] // 10), maxLineGap=20)
    if lines is None:
        return {"status": "unresolved", "confidence": 0.0, "row_direction_deg": None}
    angles = []
    for line in lines[:, 0]:
        dx, dy = float(line[2] - line[0]), float(line[3] - line[1])
        if abs(dx) + abs(dy) > 0: angles.append((np.degrees(np.arctan2(dy, dx)) + 180) % 180)
    if not angles:
        return {"status": "unresolved", "confidence": 0.0, "row_direction_deg": None}
    histogram, bins = np.histogram(angles, bins=18, range=(0, 180))
    index = int(np.argmax(histogram))
    return {"status": "pass", "confidence": float(histogram[index] / len(angles)), "row_direction_deg": float((bins[index] + bins[index + 1]) / 2), "line_count": len(angles)}


def visible_water_heuristic(segmentation: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    water_pct = float(segmentation.get("visible_water_pct", 0.0))
    glare = float(quality.get("glare_ratio", 0.0))
    if glare > 0.35:
        return {"status": "uncertain", "reason": "glare_confounds_visible_water", "confidence": max(0.0, 1.0 - glare)}
    return {"status": "candidate" if water_pct >= 1.0 else "none", "area_pct": water_pct, "confidence": min(0.8, water_pct / 10.0)}


def anomaly_signature(*, current: dict[str, float], baseline: dict[str, float] | None) -> dict[str, Any]:
    if not baseline:
        return {"type": "abnormal_crop_health_signature", "status": "cold_start", "confidence": 0.25, "baseline_id": None}
    deltas = {key: float(current.get(key, 0.0) - baseline.get(key, 0.0)) for key in current}
    magnitude = sum(abs(value) for value in deltas.values()) / max(1, len(deltas))
    return {"type": "abnormal_crop_health_signature", "status": "candidate" if magnitude > 0.15 else "normal", "confidence": min(0.95, magnitude), "deltas": deltas}
