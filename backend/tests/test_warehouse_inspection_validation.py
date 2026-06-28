from types import SimpleNamespace

from backend.modules.warehouse.planning.indoor.enums import OccupancyState
from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid
from backend.modules.warehouse.service.inspection_validation import validate_inspection_path


def _grid() -> OccupancyGrid:
    grid = OccupancyGrid(1.0, 10, 10, default_state=OccupancyState.FREE)
    return grid


def _target() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        shelf_normal_local_json={"x": 1.0, "y": 0.0, "z": 0.0},
        target_point_local_json={"x_m": 5.5, "y_m": 4.5, "z_m": 1.5},
    )


def _validate(grid: OccupancyGrid, *, map_age_s: float = 0.0, battery_pct: float = 100.0):
    scan = LocalPose(4.5, 4.5, 1.5, frame_id="warehouse_map")
    start = LocalPose(1.5, 1.5, 1.0, frame_id="warehouse_map")
    return validate_inspection_path(
        targets=[_target()],
        grid=grid,
        grid_poses=[scan],
        warehouse_poses=[scan],
        warehouse_polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
        map_age_s=map_age_s,
        start_grid_pose=start,
        return_to_dock=True,
        battery_pct=battery_pct,
    )


def test_complete_inspection_path_passes() -> None:
    report = _validate(_grid())

    assert report.passed is True
    assert len(report.paths) == 2
    assert report.energy["estimated_cost_pct"] > 0


def test_low_battery_fails_return_energy_budget() -> None:
    report = _validate(_grid(), battery_pct=20.1)

    assert report.passed is False
    assert "return_energy" in {failure["check"] for failure in report.failures}


def test_stale_map_is_blocking() -> None:
    report = _validate(_grid(), map_age_s=11.0)

    assert report.passed is False
    assert "map_freshness" in {failure["check"] for failure in report.failures}


def test_inflated_wall_blocks_outbound_and_return_paths() -> None:
    grid = _grid()
    grid.set_cells(((3, y) for y in range(10)), OccupancyState.OCCUPIED)

    report = _validate(grid)

    assert report.passed is False
    assert "swept_path" in {failure["check"] for failure in report.failures}


def test_wrong_shelf_approach_direction_is_blocking() -> None:
    target = _target()
    target.shelf_normal_local_json = {"x": -1.0, "y": 0.0, "z": 0.0}
    scan = LocalPose(4.5, 4.5, 1.5, frame_id="warehouse_map")
    report = validate_inspection_path(
        targets=[target],
        grid=_grid(),
        grid_poses=[scan],
        warehouse_poses=[scan],
        warehouse_polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
        map_age_s=0.0,
        start_grid_pose=LocalPose(1.5, 1.5, 1.0),
        return_to_dock=True,
    )

    assert report.passed is False
    assert "approach_cone" in {failure["check"] for failure in report.failures}
