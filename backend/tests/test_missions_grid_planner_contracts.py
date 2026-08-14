"""Characterization tests for agricultural grid planning before file-size splits."""

from __future__ import annotations

import pytest

from backend.modules.missions.planning.grid import (
    GridPlanner,
    GridPlanResult,
    _validate_plan_limits,
    combine_grid_plans,
)


def _sample_field_polygon() -> list[tuple[float, float]]:
    return [
        (-122.0000, 37.0000),
        (-122.0018, 37.0000),
        (-122.0018, 37.00135),
        (-122.0000, 37.00135),
    ]


def test_grid_planner_rectangular_field_plan_is_stable() -> None:
    plan = GridPlanner.generate(
        _sample_field_polygon(),
        spacing_m=25.0,
        angle_deg=45.0,
        inset_m=1.0,
        row_stride=2,
    )

    assert len(plan.waypoints) == 8
    assert len(plan.work_leg_mask) == 7
    assert sum(plan.work_leg_mask) == 4
    assert plan.angle_deg == 45.0
    assert plan.spacing_m == 25.0
    assert plan.stats["rows"] == 4
    assert plan.stats["route_m"] == pytest.approx(662.3, rel=0, abs=0.1)


def test_combine_grid_plans_crosshatch_concatenates_passes() -> None:
    poly = _sample_field_polygon()
    primary = GridPlanner.generate(
        poly,
        spacing_m=25.0,
        angle_deg=45.0,
        inset_m=1.0,
        row_stride=2,
    )
    secondary = GridPlanner.generate(
        poly,
        spacing_m=25.0,
        angle_deg=135.0,
        inset_m=1.0,
        row_stride=2,
    )

    combined = combine_grid_plans([primary, secondary], poly, "crosshatch")

    assert combined.stats["passes"] == 2
    assert len(combined.waypoints) == 16
    assert combined.stats["pattern_mode"] == "crosshatch"


def test_validate_plan_limits_rejects_oversized_grid() -> None:
    oversized = GridPlanResult(
        waypoints=[],
        work_leg_mask=[],
        angle_deg=0.0,
        spacing_m=7.5,
        stats={"rows": 10_000, "waypoints": 0, "route_m": 0.0},
    )

    with pytest.raises(ValueError, match="rows"):
        _validate_plan_limits(oversized)
