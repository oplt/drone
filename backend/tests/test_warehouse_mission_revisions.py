import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.modules.warehouse.models import WarehouseInspectionMission
from backend.modules.warehouse.service.drift_guard import transform_checksum
from backend.modules.warehouse.service.mission_revisions import (
    create_mission_revision_pins,
    require_legacy_same_origin_confirmation,
    verify_mission_revision_pins,
)


def test_planning_rejects_targets_from_mixed_layout_revisions() -> None:
    db = MagicMock()
    targets = [
        SimpleNamespace(id=1, layout_version_id=10),
        SimpleNamespace(id=2, layout_version_id=11),
    ]

    with pytest.raises(HTTPException, match="one pinned warehouse layout") as error:
        asyncio.run(
            create_mission_revision_pins(
                db,
                warehouse_map_id=7,
                coordinate_frame_id=3,
                targets=targets,
                return_to_dock=True,
            )
        )

    assert error.value.status_code == 409
    db.get.assert_not_called()


def test_planning_pins_locked_layout_model_validation_and_artifacts(monkeypatch) -> None:
    from backend.modules.warehouse.planning.indoor.enums import OccupancyState
    from backend.modules.warehouse.planning.indoor.models import OccupancyGrid
    from backend.modules.warehouse.service import mission_revisions

    layout = SimpleNamespace(
        id=10,
        warehouse_map_id=7,
        version=3,
        status="locked",
        coordinate_frame_id=3,
        map_model_id=20,
    )
    model = SimpleNamespace(id=20, warehouse_map_id=7, version=5)
    frame = SimpleNamespace(id=3, transform_json={})
    warehouse_map = SimpleNamespace(meta_data={"polygon_local_m": []})
    asset = SimpleNamespace(id=40, checksum="a" * 64)
    target = SimpleNamespace(
        id=100,
        layout_version_id=10,
        scan_pose_local_json={"x_m": 1.0, "y_m": 1.0, "z_m": 1.2},
        dock_station_id=None,
    )

    grid = OccupancyGrid(
        resolution_m=0.5,
        width=10,
        height=10,
        default_state=OccupancyState.FREE,
    )
    readiness = SimpleNamespace(
        occupancy_message={"header": {"frame_id": "warehouse_map"}},
        occupancy_topic="/nvblox_node/occupancy_grid",
    )
    report = SimpleNamespace(passed=True, to_dict=lambda: {"status": "passed"})
    result = MagicMock()
    result.scalars.return_value.all.return_value = [asset]
    added = []

    async def flush() -> None:
        added[-1].id = 30

    db = MagicMock()
    db.get = AsyncMock(side_effect=[layout, model, frame, warehouse_map])
    db.execute = AsyncMock(return_value=result)
    db.add.side_effect = added.append
    db.flush = AsyncMock(side_effect=flush)
    monkeypatch.setattr(
        mission_revisions,
        "refresh_structure_input_readiness",
        AsyncMock(return_value=readiness),
    )
    monkeypatch.setattr(mission_revisions, "occupancy_grid_from_ros_yaml", lambda _msg: grid)
    monkeypatch.setattr(mission_revisions, "validate_inspection_path", lambda **_kwargs: report)
    monkeypatch.setattr(
        mission_revisions,
        "validate_inspection_path_esdf",
        lambda **_kwargs: {"warnings": [], "failures": []},
    )

    pins = asyncio.run(
        create_mission_revision_pins(
            db,
            warehouse_map_id=7,
            coordinate_frame_id=3,
            targets=[target],
            return_to_dock=True,
        )
    )

    assert pins.layout_version_id == 10
    assert pins.layout_version == 3
    assert pins.map_model_id == 20
    assert pins.map_model_version == 5
    assert pins.validation_result_id == 30
    assert pins.artifact_checksums == {"40": "a" * 64}
    assert added[0].layout_version_id == 10
    assert added[0].coordinate_frame_id == 3
    assert added[0].map_model_id == 20


def test_execution_rejects_changed_artifact_checksum() -> None:
    mission = WarehouseInspectionMission(
        warehouse_map_id=7,
        name="Pinned mission",
        coordinate_frame_id=3,
        layout_version_id=10,
        map_model_id=20,
        validation_result_id=30,
        artifact_checksums_json={"40": "a" * 64},
    )
    layout = SimpleNamespace(
        id=10,
        status="locked",
        coordinate_frame_id=3,
        map_model_id=20,
    )
    model = SimpleNamespace(id=20, coordinate_frame_id=3)
    validation = SimpleNamespace(id=30, status="passed", created_at=datetime.now(UTC))
    transform = {
        "translation": {"x": 0, "y": 0, "z": 0},
        "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
    }
    covariance = [0.0] * 36
    frame = SimpleNamespace(
        id=3,
        status="locked",
        transform_json=transform,
        transform_timestamp=datetime.now(UTC),
        max_age_s=300,
        covariance_json=covariance,
        confidence=1.0,
        transform_checksum=transform_checksum(transform),
    )
    asset = SimpleNamespace(id=40, checksum="b" * 64)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [asset]
    db = MagicMock()
    db.get = AsyncMock(side_effect=[layout, frame, model, validation])
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(HTTPException, match="checksums no longer match") as error:
        asyncio.run(verify_mission_revision_pins(db, mission))

    assert error.value.status_code == 409


def test_legacy_mission_is_non_repeatable_without_same_origin_confirmation() -> None:
    mission = WarehouseInspectionMission(warehouse_map_id=7, name="Legacy")

    with pytest.raises(HTTPException) as error:
        require_legacy_same_origin_confirmation(mission, same_origin_confirmed=False)

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "legacy_mission_non_repeatable"


def test_legacy_mission_accepts_explicit_same_origin_confirmation() -> None:
    mission = WarehouseInspectionMission(warehouse_map_id=7, name="Legacy")

    require_legacy_same_origin_confirmation(mission, same_origin_confirmed=True)
