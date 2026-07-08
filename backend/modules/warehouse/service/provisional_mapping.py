from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

ProvisionalEntityState = Literal[
    "candidate",
    "user_labeled",
    "confirmed",
    "locked",
]

LiveProvisionalState = Literal[
    "provisional",
    "needs_more_coverage",
    "needs_review",
    "ready_to_publish",
    "locked",
]


@dataclass
class ProvisionalMappingEpoch:
    epoch_id: str
    revision: int = 0
    slam_frame_id: str = "scan_odom"
    started_at_monotonic: float = field(default_factory=time.monotonic)
    last_update_monotonic: float = field(default_factory=time.monotonic)
    confidence: float = 0.0
    displacement_m: float = 0.0


_EPOCHS: dict[int, ProvisionalMappingEpoch] = {}


def map_candidate_status(status: str) -> ProvisionalEntityState:
    mapping = {
        "provisional": "candidate",
        "needs_review": "user_labeled",
        "accepted": "confirmed",
        "rejected": "candidate",
    }
    return mapping.get(status, "candidate")  # type: ignore[return-value]


def begin_provisional_epoch(*, warehouse_map_id: int, epoch_id: str) -> ProvisionalMappingEpoch:
    epoch = ProvisionalMappingEpoch(epoch_id=str(epoch_id))
    _EPOCHS[int(warehouse_map_id)] = epoch
    return epoch


def note_provisional_update(
    *,
    warehouse_map_id: int,
    confidence: float,
    displacement_m: float = 0.0,
) -> ProvisionalMappingEpoch | None:
    epoch = _EPOCHS.get(int(warehouse_map_id))
    if epoch is None:
        return None
    epoch.revision += 1
    epoch.last_update_monotonic = time.monotonic()
    epoch.confidence = max(0.0, min(1.0, float(confidence)))
    epoch.displacement_m = max(0.0, float(displacement_m))
    return epoch


def provisional_epoch_snapshot(warehouse_map_id: int) -> dict[str, Any] | None:
    epoch = _EPOCHS.get(int(warehouse_map_id))
    if epoch is None:
        return None
    age_s = max(0.0, time.monotonic() - epoch.last_update_monotonic)
    return {
        "epoch_id": epoch.epoch_id,
        "revision": epoch.revision,
        "slam_frame_id": epoch.slam_frame_id,
        "confidence": epoch.confidence,
        "displacement_m": epoch.displacement_m,
        "age_s": age_s,
        "stale": age_s > 10.0 or epoch.confidence < 0.5,
    }


def block_executable_mission(*, coordinate_frame_status: str, localization_method: str | None) -> bool:
    if coordinate_frame_status != "locked":
        return True
    method = str(localization_method or "").strip().lower()
    return method in {"live_slam", "provisional_slam", "scan_provisional"}


def _bbox_center(bbox: list[float]) -> dict[str, float] | None:
    if len(bbox) != 6:
        return None
    try:
        values = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return None
    return {
        "x_m": (values[0] + values[3]) * 0.5,
        "y_m": (values[1] + values[4]) * 0.5,
        "z_m": (values[2] + values[5]) * 0.5,
    }


def _chunk_confidence(chunk: dict[str, Any], coverage_percent: float | None) -> float:
    points = max(0, int(chunk.get("point_count") or 0))
    point_score = min(1.0, points / 10_000.0)
    coverage_score = 0.4 if coverage_percent is None else max(0.0, min(1.0, coverage_percent / 100.0))
    source = str(chunk.get("source") or chunk.get("layer") or "")
    source_score = 1.0 if source.startswith(("nvblox", "rgbd")) else 0.65
    return round(max(0.1, min(0.95, 0.45 * point_score + 0.35 * coverage_score + 0.20 * source_score)), 3)


def live_candidate_state(
    *,
    confidence: float,
    coverage_percent: float | None,
    nvblox_ready: bool,
    missing_point_cloud: bool,
) -> LiveProvisionalState:
    if missing_point_cloud or coverage_percent is None or coverage_percent < 55.0:
        return "needs_more_coverage"
    if confidence < 0.55:
        return "needs_review"
    if coverage_percent >= 90.0 and nvblox_ready and confidence >= 0.75:
        return "ready_to_publish"
    return "provisional"


def provisional_candidates_from_live_update(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Derive ephemeral in-flight layout hints from live map chunks.

    These hints are intentionally not persisted and are never inspection-ready.
    The post-flight extraction/review path remains the only activation path.
    """
    health = payload.get("health") if isinstance(payload.get("health"), dict) else {}
    coverage = health.get("coverage_percent")
    coverage_percent = float(coverage) if isinstance(coverage, (int, float)) else None
    nvblox_ready = bool(health.get("nvblox_ready"))
    missing_point_cloud = bool(health.get("missing_point_cloud"))
    candidates: list[dict[str, Any]] = []
    repair_hints: list[dict[str, Any]] = []
    changed_chunks = payload.get("changed_chunks") if isinstance(payload.get("changed_chunks"), list) else []

    for chunk in changed_chunks[:20]:
        if not isinstance(chunk, dict):
            continue
        bbox = chunk.get("bbox_local_m")
        if not isinstance(bbox, list):
            continue
        center = _bbox_center(bbox)
        if center is None:
            continue
        confidence = _chunk_confidence(chunk, coverage_percent)
        state = live_candidate_state(
            confidence=confidence,
            coverage_percent=coverage_percent,
            nvblox_ready=nvblox_ready,
            missing_point_cloud=missing_point_cloud,
        )
        source = str(chunk.get("source") or chunk.get("layer") or "live_map")
        sequence = int(chunk.get("sequence") or 0)
        chunk_id = str(chunk.get("id") or sequence)
        candidate = {
            "entity_kind": "inspection_target",
            "identity_key": f"live/{source}/{sequence}/{chunk_id}",
            "geometry": {
                "source": source,
                "chunk_id": chunk_id,
                "bbox_local_m": list(bbox),
                "target_point": center,
                "frame_id": payload.get("frame_id") or chunk.get("frame_id"),
                "quality": {
                    "coverage_percent": coverage_percent,
                    "reasons": ["partial_live_map"],
                },
            },
            "confidence": confidence,
            "state": state,
            "review_required": state in {"needs_more_coverage", "needs_review"},
            "review_reasons": (
                ["needs_more_coverage"]
                if state == "needs_more_coverage"
                else ["low_confidence"]
                if state == "needs_review"
                else []
            ),
            "source_sequence": sequence,
            "inspection_ready": False,
        }
        candidates.append(candidate)
        if state == "needs_more_coverage":
            repair_hints.append(
                {
                    "kind": "extra_pass",
                    "reason": "needs_more_coverage",
                    "target_point": center,
                    "pose_local_m": {
                        "x": center["x_m"],
                        "y": center["y_m"],
                        "z": center["z_m"],
                        "yaw_deg": 0.0,
                        "frame_id": str(payload.get("frame_id") or chunk.get("frame_id") or "warehouse_map"),
                    },
                    "bbox_local_m": list(bbox),
                    "source_candidate": candidate["identity_key"],
                    "priority": 100 - min(95, int(confidence * 100)),
                }
            )

    coordinate_state = {
        "status": "provisional" if candidates else "needs_more_coverage",
        "inspection_ready": False,
        "candidate_count": len(candidates),
        "coverage_repair_count": len(repair_hints),
        "message": "Live detections are provisional until post-flight extraction and review.",
    }
    if any(item.get("state") == "ready_to_publish" for item in candidates):
        coordinate_state["status"] = "ready_to_publish"
    elif any(item.get("state") == "needs_review" for item in candidates):
        coordinate_state["status"] = "needs_review"
    elif repair_hints:
        coordinate_state["status"] = "needs_more_coverage"
    return candidates, repair_hints, coordinate_state
