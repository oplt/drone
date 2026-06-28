from __future__ import annotations

from typing import Literal

MissionStage = Literal[
    "localize",
    "staging",
    "transit",
    "approach",
    "hover",
    "capture",
    "exit",
    "return",
    "land",
]

INSPECTION_STAGE_ORDER: tuple[MissionStage, ...] = (
    "localize",
    "staging",
    "transit",
    "approach",
    "hover",
    "capture",
    "exit",
    "return",
    "land",
)

_LEGACY_STAGE_MAP: dict[str, MissionStage] = {
    "approach_target": "approach",
    "hover_for_scan": "hover",
    "trigger_scan": "capture",
    "exit_target": "exit",
}


def normalize_mission_stage(stage: str) -> MissionStage:
    token = str(stage or "").strip()
    if token in INSPECTION_STAGE_ORDER:
        return token  # type: ignore[return-value]
    return _LEGACY_STAGE_MAP.get(token, "transit")
