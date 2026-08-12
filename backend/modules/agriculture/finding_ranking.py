"""Versioned finding-ranking policy for prioritized agronomic work queues.

Observations (already clustered detections) are treated as findings. Ranking is
explainable and never presents model confidence as agronomic certainty.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

RANKING_POLICY_VERSION = "finding_rank_v1"
DEFAULT_FINDING_LIMIT = 25

DisplayStatus = Literal["shown", "labeled_low_confidence", "withheld"]

# Policy thresholds (documented in factors payload for explainability).
MIN_CONFIDENCE_SHOW = 0.35
MIN_CONFIDENCE_WITHHOLD = 0.15
TELEMETRY_WITHHOLD_STATUSES = frozenset({"unresolved"})
TELEMETRY_LABEL_STATUSES = frozenset({"low_confidence"})
NOVELTY_WEIGHT = {
    "new": 1.0,
    "expanding": 0.9,
    "unknown": 0.55,
    "stable": 0.4,
    "improving": 0.25,
    "resolved": 0.1,
}
REVIEW_WEIGHT = {
    "unreviewed": 1.0,
    "assigned": 0.95,
    "confirmed": 0.35,
    "relabelled": 0.4,
    "rejected": 0.0,
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _novelty_key(observation: Any, change_state: str | None) -> str:
    if change_state:
        return str(change_state)
    trend = str(getattr(observation, "trend", None) or "unknown")
    return trend if trend in NOVELTY_WEIGHT else "unknown"


def _crop_context_factor(observation: Any, crop_context: dict[str, Any] | None) -> tuple[float, str]:
    if not crop_context:
        return 0.5, "crop_context_unavailable"
    observation_type = str(getattr(observation, "observation_type", "") or "")
    focus = {str(item).lower() for item in (crop_context.get("priority_issue_types") or [])}
    if focus and observation_type.lower() in focus:
        return 1.0, "matches_crop_priority_issue"
    if crop_context.get("crop_type"):
        return 0.7, "crop_profile_present"
    return 0.5, "crop_context_partial"


def score_finding(
    observation: Any,
    *,
    change_state: str | None = None,
    crop_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one observation as a finding with an explainable factor breakdown."""
    severity = _clamp(float(getattr(observation, "severity", 0.0) or 0.0))
    confidence = _clamp(float(getattr(observation, "confidence", 0.0) or 0.0))
    area_m2 = float(getattr(observation, "area_m2", None) or 0.0)
    evidence_count = len(getattr(observation, "evidence_ids", None) or [])
    georef_status = str(getattr(observation, "georef_status", "unresolved") or "unresolved")
    review_state = str(getattr(observation, "review_state", "unreviewed") or "unreviewed")
    merged_into = getattr(observation, "merged_into_id", None)

    area_factor = _clamp((max(area_m2, 1.0) ** 0.5) / 20.0)
    count_factor = _clamp(0.35 + 0.15 * min(evidence_count, 4))
    novelty_key = _novelty_key(observation, change_state)
    novelty_factor = NOVELTY_WEIGHT.get(novelty_key, 0.55)
    review_factor = REVIEW_WEIGHT.get(review_state, 0.5)
    crop_factor, crop_reason = _crop_context_factor(observation, crop_context)

    if georef_status in TELEMETRY_WITHHOLD_STATUSES:
        telemetry_factor = 0.15
        telemetry_reason = "georef_unresolved"
    elif georef_status in TELEMETRY_LABEL_STATUSES:
        telemetry_factor = 0.45
        telemetry_reason = "georef_low_confidence"
    else:
        telemetry_factor = 1.0
        telemetry_reason = "georef_resolved"

    display_status: DisplayStatus = "shown"
    withhold_reasons: list[str] = []
    if merged_into:
        display_status = "withheld"
        withhold_reasons.append("merged_into_parent")
    if review_state == "rejected":
        display_status = "withheld"
        withhold_reasons.append("review_rejected")
    if confidence < MIN_CONFIDENCE_WITHHOLD:
        display_status = "withheld"
        withhold_reasons.append("confidence_below_withhold_threshold")
    elif georef_status in TELEMETRY_WITHHOLD_STATUSES and confidence < MIN_CONFIDENCE_SHOW:
        display_status = "withheld"
        withhold_reasons.append("low_telemetry_and_confidence")
    elif confidence < MIN_CONFIDENCE_SHOW or georef_status in TELEMETRY_LABEL_STATUSES:
        display_status = "labeled_low_confidence"
        withhold_reasons.append(
            "confidence_below_show_threshold"
            if confidence < MIN_CONFIDENCE_SHOW
            else "telemetry_low_confidence"
        )

    raw = (
        0.28 * severity
        + 0.22 * confidence
        + 0.14 * area_factor
        + 0.08 * count_factor
        + 0.12 * novelty_factor
        + 0.08 * telemetry_factor
        + 0.05 * crop_factor
        + 0.03 * review_factor
    )
    if display_status == "withheld":
        score = 0.0
    elif display_status == "labeled_low_confidence":
        score = _clamp(raw * 0.55)
    else:
        score = _clamp(raw)

    factors = {
        "severity": {"value": severity, "weight": 0.28, "contribution": round(0.28 * severity, 4)},
        "confidence": {
            "value": confidence,
            "weight": 0.22,
            "contribution": round(0.22 * confidence, 4),
            "thresholds": {
                "show": MIN_CONFIDENCE_SHOW,
                "withhold": MIN_CONFIDENCE_WITHHOLD,
            },
        },
        "affected_area": {
            "area_m2": area_m2,
            "factor": round(area_factor, 4),
            "weight": 0.14,
            "contribution": round(0.14 * area_factor, 4),
        },
        "evidence_count": {
            "count": evidence_count,
            "factor": round(count_factor, 4),
            "weight": 0.08,
            "contribution": round(0.08 * count_factor, 4),
        },
        "novelty": {
            "state": novelty_key,
            "factor": novelty_factor,
            "weight": 0.12,
            "contribution": round(0.12 * novelty_factor, 4),
        },
        "telemetry_quality": {
            "georef_status": georef_status,
            "factor": telemetry_factor,
            "reason": telemetry_reason,
            "weight": 0.08,
            "contribution": round(0.08 * telemetry_factor, 4),
        },
        "crop_context": {
            "factor": crop_factor,
            "reason": crop_reason,
            "weight": 0.05,
            "contribution": round(0.05 * crop_factor, 4),
        },
        "review_state": {
            "value": review_state,
            "factor": review_factor,
            "weight": 0.03,
            "contribution": round(0.03 * review_factor, 4),
        },
    }
    return {
        "observation_id": getattr(observation, "id", None),
        "score": round(score, 6),
        "display_status": display_status,
        "policy_version": RANKING_POLICY_VERSION,
        "factors": factors,
        "withhold_reasons": withhold_reasons,
        "limitations": [
            "Rank score prioritizes inspection workload; it is not agronomic certainty.",
            "Model confidence is only one calibrated input among several factors.",
        ],
    }


def rank_findings(
    observations: Iterable[Any],
    *,
    change_by_observation_id: dict[str, str] | None = None,
    crop_context: dict[str, Any] | None = None,
    limit: int = DEFAULT_FINDING_LIMIT,
    include_withheld: bool = False,
) -> list[dict[str, Any]]:
    """Return bounded, ranked findings with explanations and map hotspot payloads."""
    change_map = change_by_observation_id or {}
    ranked: list[dict[str, Any]] = []
    for observation in observations:
        if getattr(observation, "merged_into_id", None) and not include_withheld:
            continue
        scored = score_finding(
            observation,
            change_state=change_map.get(str(getattr(observation, "id", ""))),
            crop_context=crop_context,
        )
        if scored["display_status"] == "withheld" and not include_withheld:
            continue
        ranked.append(
            {
                **scored,
                "finding_id": str(getattr(observation, "id")),
                "observation_id": str(getattr(observation, "id")),
                "observation_type": getattr(observation, "observation_type", None),
                "geometry_geojson": getattr(observation, "geometry_geojson", None) or {},
                "severity": float(getattr(observation, "severity", 0.0) or 0.0),
                "confidence": float(getattr(observation, "confidence", 0.0) or 0.0),
                "area_m2": getattr(observation, "area_m2", None),
                "georef_status": getattr(observation, "georef_status", None),
                "review_state": getattr(observation, "review_state", None),
                "evidence_ids": list(getattr(observation, "evidence_ids", None) or []),
                "model_version": getattr(observation, "model_version", None),
                "provenance": getattr(observation, "provenance", None) or {},
                "assigned_to_user_id": getattr(observation, "assigned_to_user_id", None),
                "merged_into_id": getattr(observation, "merged_into_id", None),
                "member_observation_ids": list(
                    getattr(observation, "member_observation_ids", None) or []
                ),
            }
        )
    ranked.sort(
        key=lambda item: (
            0 if item["display_status"] == "shown" else 1,
            -float(item["score"]),
            str(item["finding_id"]),
        )
    )
    output: list[dict[str, Any]] = []
    for index, item in enumerate(ranked[: max(1, limit)], start=1):
        output.append({**item, "rank": index})
    return output
