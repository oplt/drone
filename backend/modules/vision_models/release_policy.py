from __future__ import annotations

from dataclasses import dataclass
from typing import Any

POLICY_VERSION = "vision-release-policy.v1"
KNOWN_CAPABILITIES = {
    "object_detection",
    "stand_count",
    "weed_detection",
    "crop_health",
    "canopy_cover",
    "row_detection",
    "standing_water",
}


@dataclass(frozen=True)
class ReleasePolicyResult:
    eligible: bool
    reasons: tuple[str, ...]
    metrics_snapshot: dict[str, Any]
    policy_version: str = POLICY_VERSION


def evaluate_release(
    *,
    status: str,
    metrics: dict[str, Any],
    weights_uri: str,
    checksum: str,
    capability_id: str,
    minimum_map50: float,
) -> ReleasePolicyResult:
    """Evaluate the bounded, server-owned policy used by every promotion."""
    reasons: list[str] = []
    summary = metrics.get("summary")
    snapshot = dict(summary) if isinstance(summary, dict) else {}
    map50 = snapshot.get("map50")
    if status != "candidate":
        reasons.append("model version must be a candidate")
    if not weights_uri or not checksum:
        reasons.append("model artifact weights and checksum are required")
    if capability_id not in KNOWN_CAPABILITIES:
        reasons.append("model capability is not recognized")
    if not isinstance(map50, (int, float)) or float(map50) < minimum_map50:
        reasons.append(f"evaluation map50 must be at least {minimum_map50:g}")
    return ReleasePolicyResult(
        eligible=not reasons,
        reasons=tuple(reasons),
        metrics_snapshot=snapshot,
    )
