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
