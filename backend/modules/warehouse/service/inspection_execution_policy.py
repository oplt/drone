from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ExecutionAction = Literal["continue", "replan", "return_to_dock", "abort_land"]


@dataclass(frozen=True)
class InspectionExecutionPolicy:
    max_replans_per_leg: int = 2
    abort_on_version_change: bool = True
    abort_on_tf_loss: bool = True


def execution_action(
    *, reason: str, replan_attempts: int, policy: InspectionExecutionPolicy
) -> ExecutionAction:
    if reason in {"obstacle_changed", "path_blocked"}:
        return "replan" if replan_attempts < policy.max_replans_per_leg else "return_to_dock"
    if reason in {"version_changed", "tf_lost", "localization_unhealthy"}:
        return "abort_land" if policy.abort_on_tf_loss else "return_to_dock"
    if reason in {"battery_low", "return_margin_low"}:
        return "return_to_dock"
    return "continue"
