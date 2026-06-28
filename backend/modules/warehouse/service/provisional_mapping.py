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
