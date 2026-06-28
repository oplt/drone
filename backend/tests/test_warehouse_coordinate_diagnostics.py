from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.modules.warehouse.service.coordinate_diagnostics import build_coordinate_diagnostics
from backend.modules.warehouse.service.drift_guard import transform_checksum

IDENTITY = {
    "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
}
COVARIANCE = [0.0] * 36
COVARIANCE[0] = COVARIANCE[7] = COVARIANCE[14] = 0.01


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class _FakeSession:
    def __init__(self, responses: list[_FakeResult]):
        self._responses = list(responses)

    async def execute(self, _stmt):
        if not self._responses:
            raise AssertionError("unexpected execute()")
        return self._responses.pop(0)


def _locked_frame(*, frame_id: int = 1, version: int = 1) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=frame_id,
        version=version,
        status="locked",
        parent_frame_id="warehouse_map",
        child_frame_id="odom",
        confidence=0.95,
        localization_method="operator_survey",
        transform_json=IDENTITY,
        transform_timestamp=now - timedelta(seconds=2),
        max_age_s=300.0,
        covariance_json=COVARIANCE,
        transform_checksum=transform_checksum(IDENTITY),
        locked_at=now,
    )


def _locked_layout(*, layout_id: int = 10, coordinate_frame_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=layout_id,
        version=1,
        revision=1,
        status="locked",
        coordinate_frame_id=coordinate_frame_id,
        provenance_status="confirmed",
        locked_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_coordinate_diagnostics_reports_missing_locked_frame(monkeypatch) -> None:
    async def _fake_map_odom_probe(**_kwargs):
        return {"tf_ok": False, "detail": "tf missing"}

    async def _fake_tree_probe(**_kwargs):
        return {"tf_ok": False, "missing_edges": ["warehouse_map->odom"], "edges": []}

    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.probe_mapping_tf_degraded",
        _fake_map_odom_probe,
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.probe_warehouse_ros_tf_tree",
        _fake_tree_probe,
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.refresh_slam_localization_from_ros",
        lambda **_: {"ingested": False},
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.slam_localization_snapshot",
        lambda **_: {"healthy": False, "confidence": 0.0, "age_ms": 5000.0},
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.provisional_epoch_snapshot",
        lambda *_: None,
    )
    session = _FakeSession(
        [
            _FakeResult(None),
            _FakeResult(None),
            _FakeResult(None),
            _FakeResult(None),
        ]
    )
    report = await build_coordinate_diagnostics(session, warehouse_map_id=7)
    assert report["mission_ready"] is False
    codes = {issue["code"] for issue in report["blocking_issues"]}
    assert "no_locked_coordinate_frame" in codes
    assert "no_locked_layout_version" in codes


@pytest.mark.asyncio
async def test_coordinate_diagnostics_ready_when_frame_and_layout_locked(monkeypatch) -> None:
    async def _fake_map_odom_probe(**_kwargs):
        return {"tf_ok": True, "detail": None}

    async def _fake_tree_probe(**_kwargs):
        return {
            "tf_ok": True,
            "edge_count": 8,
            "ok_count": 8,
            "missing_edges": [],
            "edges": [],
        }

    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.probe_mapping_tf_degraded",
        _fake_map_odom_probe,
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.probe_warehouse_ros_tf_tree",
        _fake_tree_probe,
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.refresh_slam_localization_from_ros",
        lambda **_: {"ingested": False},
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.slam_localization_snapshot",
        lambda **_: {"healthy": True, "confidence": 0.9, "age_ms": 10.0},
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.coordinate_diagnostics.provisional_epoch_snapshot",
        lambda *_: None,
    )
    frame = _locked_frame()
    layout = _locked_layout(coordinate_frame_id=int(frame.id))
    session = _FakeSession(
        [
            _FakeResult(frame),
            _FakeResult(frame),
            _FakeResult(layout),
            _FakeResult(layout),
            _FakeResult(2),
            _FakeResult(4),
            _FakeResult(8),
            _FakeResult(16),
        ]
    )
    report = await build_coordinate_diagnostics(session, warehouse_map_id=7)
    assert report["mission_ready"] is True
    assert report["coordinate_frame"]["version"] == 1
    assert report["layout_version"]["id"] == 10
    assert report["entity_counts"] == {
        "aisles": 2,
        "racks": 4,
        "shelves": 8,
        "bins": 16,
    }
    assert report["ros_tf_tree"]["tf_ok"] is True
