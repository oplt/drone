import asyncio
import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.modules.warehouse.models import WarehouseCoordinateFrame, WarehouseMapSetupVersion
from backend.modules.warehouse.service.drift_guard import (
    TransformDriftMonitor,
    ensure_no_active_missions_for_frame_change,
    transform_checksum,
    validate_localization_evidence,
    validate_scale_calibration,
)

IDENTITY = {
    "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
}
COVARIANCE = [0.0] * 36
COVARIANCE[0] = COVARIANCE[7] = COVARIANCE[14] = 0.01


def test_locked_localization_requires_fresh_covariance_and_confidence() -> None:
    now = datetime.now(UTC)
    evidence = validate_localization_evidence(
        transform=IDENTITY,
        transform_timestamp=now - timedelta(seconds=2),
        max_age_s=5,
        covariance=COVARIANCE,
        confidence=0.9,
        now=now,
    )
    assert evidence["age_s"] == pytest.approx(2)
    assert evidence["checksum_sha256"] == transform_checksum(IDENTITY)

    with pytest.raises(ValueError, match="stale"):
        validate_localization_evidence(
            transform=IDENTITY,
            transform_timestamp=now - timedelta(seconds=6),
            max_age_s=5,
            covariance=COVARIANCE,
            confidence=0.9,
            now=now,
        )
    with pytest.raises(ValueError, match="6x6"):
        validate_localization_evidence(
            transform=IDENTITY,
            transform_timestamp=now,
            max_age_s=5,
            covariance=[],
            confidence=0.9,
            now=now,
        )


def test_scale_calibration_rejects_non_metric_or_bad_known_distance() -> None:
    assert validate_scale_calibration(
        scale=1.0,
        map_resolution_m=0.05,
        expected_distance_m=10.0,
        measured_distance_m=10.1,
    )["relative_error"] == pytest.approx(0.01)
    with pytest.raises(ValueError, match="scale"):
        validate_scale_calibration(
            scale=0.01,
            map_resolution_m=0.05,
            expected_distance_m=None,
            measured_distance_m=None,
        )
    with pytest.raises(ValueError, match="exceeds"):
        validate_scale_calibration(
            scale=1.0,
            map_resolution_m=0.05,
            expected_distance_m=10.0,
            measured_distance_m=10.3,
        )


def _transform(x: float, yaw_rad: float = 0.0):
    return SimpleNamespace(
        transform=SimpleNamespace(
            translation=SimpleNamespace(x=x, y=0.0, z=0.0),
            rotation=SimpleNamespace(
                x=0.0,
                y=0.0,
                z=math.sin(yaw_rad / 2),
                w=math.cos(yaw_rad / 2),
            ),
        )
    )


def test_transform_delta_monitor_alarms_on_translation_or_yaw_jump() -> None:
    monitor = TransformDriftMonitor(max_translation_jump_m=0.5, max_yaw_jump_rad=0.2)
    assert monitor.observe("camera", _transform(0.0)) is None
    assert monitor.observe("camera", _transform(0.1)).jumped is False
    assert monitor.observe("camera", _transform(1.0)).jumped is True


def test_active_mission_freezes_coordinate_revision() -> None:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one.return_value = 1
    db.execute = AsyncMock(return_value=result)
    with pytest.raises(HTTPException, match="frozen"):
        asyncio.run(ensure_no_active_missions_for_frame_change(db, warehouse_map_id=7))


def test_drift_prevention_columns_are_persisted() -> None:
    frame_columns = WarehouseCoordinateFrame.__table__.columns
    setup_columns = WarehouseMapSetupVersion.__table__.columns
    assert all(name in frame_columns for name in ("transform_timestamp", "max_age_s", "transform_checksum"))
    assert all(name in setup_columns for name in ("map_resolution_m", "scale", "scale_calibration_json"))
