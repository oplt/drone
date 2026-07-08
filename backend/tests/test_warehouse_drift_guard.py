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
from backend.modules.warehouse.routers.coordinate_frames import (
    CoordinateFrameCreate,
    _commissioning_report,
    _require_commissioned_frame,
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
    assert all(
        name in frame_columns
        for name in ("transform_timestamp", "max_age_s", "transform_checksum", "meta_data")
    )
    assert all(name in setup_columns for name in ("map_resolution_m", "scale", "scale_calibration_json"))


class _CountResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


def _commissioned_payload(**overrides) -> CoordinateFrameCreate:
    data = {
        "transform": {
            "translation": {"x": 1.0, "y": 0.5, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
        "source": "commissioning",
        "confidence": 0.85,
        "covariance": COVARIANCE,
        "transform_timestamp": datetime.now(UTC),
        "max_age_s": 300.0,
        "localization_method": "lidar_slam",
        "commissioning_evidence": {
            "dock_pose_confirmed": True,
            "sensor_calibration_hash": "calib-123",
            "localization_checks": [
                {
                    "kind": "slam",
                    "passed": True,
                    "confidence": 0.9,
                    "residual_m": 0.04,
                    "yaw_residual_deg": 1.2,
                },
                {
                    "kind": "landmark",
                    "passed": True,
                    "confidence": 0.82,
                    "residual_m": 0.08,
                    "yaw_residual_deg": 2.0,
                },
            ],
        },
        "lock": True,
    }
    data.update(overrides)
    return CoordinateFrameCreate.model_validate(data)


def test_commissioning_report_requires_two_independent_checks() -> None:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_CountResult(0), _CountResult(0)])
    payload = _commissioned_payload(
        commissioning_evidence={
            "dock_pose_confirmed": True,
            "sensor_calibration_hash": "calib-123",
            "localization_checks": [
                {"kind": "slam", "passed": True, "confidence": 0.9, "residual_m": 0.04}
            ],
        }
    )

    report = asyncio.run(_commissioning_report(db, warehouse_map_id=7, payload=payload))

    codes = {issue["code"] for issue in report["issues"]}
    assert "landmark_check_missing" in codes
    assert "independent_checks_missing" in codes
    assert report["residual_metrics"]["translation_residual_max_m"] == pytest.approx(0.04)


def test_commissioning_report_accepts_slam_and_landmark_evidence() -> None:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_CountResult(1), _CountResult(1)])

    report = asyncio.run(
        _commissioning_report(db, warehouse_map_id=7, payload=_commissioned_payload())
    )

    assert report["passed"] is True
    assert report["issues"] == []
    assert set(report["check_kinds"]) == {"landmark", "slam"}
    assert report["residual_metrics"]["translation_residual_count"] == 2


def test_commissioning_rejects_identity_without_explicit_simulation() -> None:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_CountResult(1), _CountResult(1)])
    payload = _commissioned_payload(transform=IDENTITY)

    report = asyncio.run(_commissioning_report(db, warehouse_map_id=7, payload=payload))

    assert "identity_transform_not_allowed" in {issue["code"] for issue in report["issues"]}


def test_require_commissioned_frame_rejects_checksum_mismatch_style_metadata_gap() -> None:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_CountResult(0), _CountResult(0)])
    row = SimpleNamespace(
        transform_json={"translation": {"x": 1, "y": 0, "z": 0}, "rotation": IDENTITY["rotation"]},
        covariance_json=COVARIANCE,
        confidence=0.9,
        localization_method="lidar_slam",
        meta_data={
            "commissioning_evidence": {
                "localization_checks": [
                    {"kind": "slam", "passed": True, "confidence": 0.9, "residual_m": 0.02}
                ]
            }
        },
    )

    with pytest.raises(HTTPException):
        asyncio.run(_require_commissioned_frame(db, warehouse_map_id=7, row=row))
