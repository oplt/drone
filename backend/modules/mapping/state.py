from __future__ import annotations

from typing import Final

MAPPING_JOB_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "uploading", "processing", "ready", "failed"}
)

FIELD_MODEL_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "processing", "ready", "failed"}
)

_VALID_MAPPING_JOB_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "pending": frozenset({"uploading", "processing", "failed"}),
    "uploading": frozenset({"processing", "failed"}),
    "processing": frozenset({"ready", "failed"}),
    "ready": frozenset(),
    "failed": frozenset(),
}

_VALID_FIELD_MODEL_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "pending": frozenset({"processing", "failed"}),
    "processing": frozenset({"ready", "failed"}),
    "ready": frozenset(),
    "failed": frozenset(),
}


def validate_mapping_job_transition(current: str, new: str) -> bool:
    """Return True when ``new`` is an allowed MappingJob status from ``current``."""
    if current == new:
        return True
    if current not in MAPPING_JOB_STATUSES or new not in MAPPING_JOB_STATUSES:
        return False
    return new in _VALID_MAPPING_JOB_TRANSITIONS[current]


def validate_field_model_transition(current: str, new: str) -> bool:
    """Return True when ``new`` is an allowed FieldModel status from ``current``."""
    if current == new:
        return True
    if current not in FIELD_MODEL_STATUSES or new not in FIELD_MODEL_STATUSES:
        return False
    return new in _VALID_FIELD_MODEL_TRANSITIONS[current]


def assert_mapping_job_transition(current: str, new: str) -> None:
    if not validate_mapping_job_transition(current, new):
        raise ValueError(f"Invalid MappingJob status transition: {current!r} -> {new!r}")
