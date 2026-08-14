from __future__ import annotations

import pytest

from backend.modules.mapping.state import (
    assert_mapping_job_transition,
    validate_field_model_transition,
    validate_mapping_job_transition,
)


@pytest.mark.parametrize(
    ("current", "new", "allowed"),
    [
        ("pending", "uploading", True),
        ("pending", "processing", True),
        ("pending", "ready", False),
        ("uploading", "processing", True),
        ("processing", "ready", True),
        ("processing", "failed", True),
        ("ready", "processing", False),
        ("failed", "pending", False),
        ("ready", "ready", True),
    ],
)
def test_mapping_job_transition_matrix(current: str, new: str, allowed: bool) -> None:
    assert validate_mapping_job_transition(current, new) is allowed


def test_mapping_job_transition_rejects_unknown_status() -> None:
    assert validate_mapping_job_transition("pending", "bogus") is False
    assert validate_mapping_job_transition("bogus", "pending") is False


def test_assert_mapping_job_transition_raises() -> None:
    with pytest.raises(ValueError, match="Invalid MappingJob status transition"):
        assert_mapping_job_transition("ready", "processing")


@pytest.mark.parametrize(
    ("current", "new", "allowed"),
    [
        ("pending", "processing", True),
        ("processing", "ready", True),
        ("ready", "failed", False),
        ("failed", "pending", False),
    ],
)
def test_field_model_transition_matrix(current: str, new: str, allowed: bool) -> None:
    assert validate_field_model_transition(current, new) is allowed
