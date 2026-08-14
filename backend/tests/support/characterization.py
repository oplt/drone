"""Helpers for golden-input / golden-output characterization tests before file splits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_fixture(relative_path: str) -> Any:
    path = Path(__file__).resolve().parents[2] / "fixtures" / "characterization" / relative_path
    return json.loads(path.read_text(encoding="utf-8"))


def assert_coordinate_sequence_stable(
    actual: list[tuple[float, float]],
    expected: list[tuple[float, float]],
    *,
    tol: float = 1e-6,
) -> None:
    assert len(actual) == len(expected)
    for (ax, ay), (ex, ey) in zip(actual, expected, strict=True):
        assert abs(ax - ex) <= tol, f"lat/lon mismatch: {ax}!={ex}"
        assert abs(ay - ey) <= tol, f"lat/lon mismatch: {ay}!={ey}"
