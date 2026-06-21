from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

PatrolAiTask = Literal[
    "intruder_detection",
    "vehicle_detection",
    "fence_breach_detection",
    "motion_detection",
]

PATROL_AI_TASKS: tuple[PatrolAiTask, ...] = (
    "intruder_detection",
    "vehicle_detection",
    "fence_breach_detection",
    "motion_detection",
)

VEHICLE_LABELS = frozenset({"car", "truck", "bus", "motorcycle", "bicycle"})
DETECTOR_BASE_LABELS = frozenset(
    {"person", "car", "truck", "bus", "motorcycle", "bicycle", "dog", "cat"}
)


def coerce_ai_tasks(tasks: Iterable[str] | None) -> tuple[PatrolAiTask, ...]:
    if tasks is None:
        return PATROL_AI_TASKS

    normalized: list[PatrolAiTask] = []
    seen: set[str] = set()
    for raw in tasks:
        key = str(raw or "").strip().lower()
        if not key:
            continue
        if key not in PATROL_AI_TASKS:
            raise ValueError(
                f"Unsupported patrol AI task '{raw}'. Supported tasks: {', '.join(PATROL_AI_TASKS)}"
            )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)  # type: ignore[arg-type]

    if not normalized:
        return PATROL_AI_TASKS
    return tuple(normalized)


def frozenset_ai_tasks(tasks: Iterable[str] | None) -> frozenset[str]:
    return frozenset(coerce_ai_tasks(tasks))


def map_anomaly_to_ai_task(event_type: str, label: str) -> str:
    normalized_event = str(event_type or "").strip().lower()
    normalized_label = str(label or "").strip().lower()

    if normalized_event in {"intrusion_detected", "loitering"}:
        if normalized_label in VEHICLE_LABELS:
            return "vehicle_detection"
        return "intruder_detection"

    if normalized_event == "restricted_zone_entry":
        if normalized_label in VEHICLE_LABELS:
            return "vehicle_detection"
        if normalized_label == "person":
            return "fence_breach_detection"
        return "fence_breach_detection"

    if normalized_event in {"scene_motion", "motion_detected"}:
        return "motion_detection"

    if normalized_label in VEHICLE_LABELS:
        return "vehicle_detection"
    return "intruder_detection"


def anomaly_allowed(event_type: str, label: str, enabled_tasks: frozenset[str]) -> bool:
    if not enabled_tasks:
        return True
    return map_anomaly_to_ai_task(event_type, label) in enabled_tasks


def detector_labels_for_tasks(enabled_tasks: frozenset[str]) -> frozenset[str]:
    if not enabled_tasks:
        return DETECTOR_BASE_LABELS

    labels: set[str] = set()
    if "intruder_detection" in enabled_tasks:
        labels.update({"person", "dog", "cat"})
    if "vehicle_detection" in enabled_tasks:
        labels.update(VEHICLE_LABELS)
    if "fence_breach_detection" in enabled_tasks:
        labels.update({"person", *VEHICLE_LABELS})

    if labels:
        return frozenset(labels)

    if enabled_tasks == frozenset({"motion_detection"}):
        return frozenset()

    return DETECTOR_BASE_LABELS


def yolo_detection_enabled(enabled_tasks: frozenset[str]) -> bool:
    return bool(detector_labels_for_tasks(enabled_tasks))


def live_detection_ai_task(label: str, enabled_tasks: frozenset[str]) -> str | None:
    if not enabled_tasks:
        return "intruder_detection"

    normalized_label = str(label or "").strip().lower()
    if normalized_label in VEHICLE_LABELS and "vehicle_detection" in enabled_tasks:
        return "vehicle_detection"
    if normalized_label == "person" and "intruder_detection" in enabled_tasks:
        return "intruder_detection"
    if normalized_label in DETECTOR_BASE_LABELS and "fence_breach_detection" in enabled_tasks:
        return "fence_breach_detection"
    return None


def apply_active_ai_tasks(
    *,
    enabled_tasks: Sequence[str] | None,
    detector: object,
    anomaly_scorer: object,
) -> frozenset[str]:
    """Configure detector/scorer for the active mission AI task set."""
    active = frozenset_ai_tasks(enabled_tasks)
    labels = detector_labels_for_tasks(active)

    if hasattr(detector, "set_allowed_labels"):
        detector.set_allowed_labels(labels)

    if hasattr(anomaly_scorer, "set_enabled_tasks"):
        anomaly_scorer.set_enabled_tasks(active)

    return active
