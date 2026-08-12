"""Offline EXP-002 detector/tracker profile evaluation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "benchmarks"
    / "exp002"
    / "fixtures"
)

GATES = {
    "max_count_error": 0.15,
    "min_small_object_recall": 0.60,
    "max_recall_drop_vs_standard": 0.05,
    "max_fragmentation_ratio": 1.35,
    "max_latency_factor_vs_standard": 2.5,
    "max_cost_factor_vs_standard": 2.0,
}


def load_fixture() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "stand_count_profiles.json").read_text(encoding="utf-8"))


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def _box_area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def small_object_recall(gt_boxes: list[list[float]], pred_boxes: list[list[float]], *, iou_threshold: float = 0.5) -> float:
    small = [box for box in gt_boxes if _box_area(box) <= 32 * 32]
    if not small:
        return 1.0
    matched = 0
    used: set[int] = set()
    for gt in small:
        best_i, best = -1, 0.0
        for index, pred in enumerate(pred_boxes):
            if index in used:
                continue
            score = _iou(gt, pred)
            if score > best:
                best_i, best = index, score
        if best_i >= 0 and best >= iou_threshold:
            used.add(best_i)
            matched += 1
    return matched / len(small)


def evaluate_profile(profile: dict[str, Any], gt: dict[str, Any]) -> dict[str, Any]:
    gt_count = float(gt["plant_count"])
    pred_count = float(profile["pred_count"])
    count_error = abs(pred_count - gt_count) / max(gt_count, 1.0)
    recall = small_object_recall(gt["boxes"], profile["boxes"])
    track_ids = profile.get("track_ids") or []
    fragmentation = (len(set(track_ids)) / max(gt_count, 1.0)) if track_ids else 1.0
    latency = float(profile["latency_s"])
    cost = float(profile["detection_work_units"])
    return {
        "profile_id": profile["id"],
        "small_object_mode": profile["small_object_mode"],
        "tracking_enabled": profile["tracking_enabled"],
        "count_error": round(count_error, 4),
        "small_object_recall": round(recall, 4),
        "fragmentation_ratio": round(fragmentation, 4),
        "latency_s": latency,
        "cost_units": cost,
    }


def gates_for(row: dict[str, Any], *, standard: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if row["count_error"] > GATES["max_count_error"]:
        failures.append("count_error")
    if row["small_object_recall"] < GATES["min_small_object_recall"]:
        failures.append("small_object_recall_floor")
    if row["small_object_recall"] + GATES["max_recall_drop_vs_standard"] < standard["small_object_recall"]:
        # allow better recall; fail only if worse than standard by more than epsilon
        if row["small_object_recall"] < standard["small_object_recall"] - GATES["max_recall_drop_vs_standard"]:
            failures.append("small_object_recall_vs_standard")
    if row["tracking_enabled"] and row["fragmentation_ratio"] > GATES["max_fragmentation_ratio"]:
        failures.append("fragmentation_ratio")
    if row["latency_s"] > standard["latency_s"] * GATES["max_latency_factor_vs_standard"]:
        failures.append("latency_factor")
    if row["cost_units"] > standard["cost_units"] * GATES["max_cost_factor_vs_standard"]:
        failures.append("cost_factor")
    return {"passed": not failures, "failures": failures}


def evaluate_detector_profiles() -> dict[str, Any]:
    fixture = load_fixture()
    gt = fixture["ground_truth"]
    rows = [evaluate_profile(profile, gt) for profile in fixture["profiles"]]
    standard = next(row for row in rows if row["profile_id"] == "A")
    scored = []
    for row in rows:
        gate = gates_for(row, standard=standard)
        scored.append({**row, **gate})
    promotable = [
        row
        for row in scored
        if row["passed"]
        and row["profile_id"] != "A"
        and (
            row["count_error"] < standard["count_error"]
            or (
                row["count_error"] <= standard["count_error"]
                and row["small_object_recall"] >= standard["small_object_recall"] + 0.05
                and row["cost_units"] <= standard["cost_units"] * 1.25
            )
        )
    ]
    # Prefer lowest cost among promotable; empty => no promotion
    promoted = min(promotable, key=lambda item: (item["count_error"], item["cost_units"]), default=None)
    return {
        "experiment": "EXP-002",
        "failure_mode": fixture["failure_mode"],
        "model_checksum": fixture["model_checksum"],
        "gates": GATES,
        "profiles": scored,
        "promoted_profile_id": promoted["profile_id"] if promoted else None,
        "adr_recommendation": "NO-GO_promotion" if promoted is None else f"GO_{promoted['profile_id']}",
        "default_recommendation": "A",
    }


def run_all() -> dict[str, Any]:
    return evaluate_detector_profiles()
