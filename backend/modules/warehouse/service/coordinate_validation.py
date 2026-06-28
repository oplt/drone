"""Structured coordinate/layout validation shared by HTTP and jobs."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    path: str
    severity: str = "error"


def validate_geometry(geometry: dict, *, path: str = "geometry") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not geometry:
        return [ValidationIssue("geometry_empty", "Geometry is empty", path, "warning")]

    def walk(value, current):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{current}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{current}[{index}]")
        elif isinstance(value, (int, float)) and not math.isfinite(value):
            issues.append(
                ValidationIssue("coordinate_non_finite", "Coordinate must be finite", current)
            )

    walk(geometry, path)
    return issues


def validate_vertical_bounds(min_z_m: float | None, max_z_m: float | None) -> list[ValidationIssue]:
    if min_z_m is not None and max_z_m is not None and min_z_m > max_z_m:
        return [ValidationIssue("vertical_bounds_reversed", "min_z_m exceeds max_z_m", "max_z_m")]
    return []
