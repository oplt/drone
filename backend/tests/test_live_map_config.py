from __future__ import annotations

from backend.modules.warehouse.service import live_map_config


def test_should_persist_raw_lidar_when_live_stream_enabled(monkeypatch) -> None:
    monkeypatch.setattr(live_map_config.settings, "warehouse_live_map_raw_lidar_enabled", True)
    monkeypatch.setattr(live_map_config.settings, "warehouse_persist_raw_lidar_layer", False)
    assert live_map_config.should_persist_raw_lidar_chunks() is True


def test_should_persist_raw_lidar_when_explicit_persist_flag(monkeypatch) -> None:
    monkeypatch.setattr(live_map_config.settings, "warehouse_live_map_raw_lidar_enabled", False)
    monkeypatch.setattr(live_map_config.settings, "warehouse_include_raw_lidar_preview", False)
    monkeypatch.setattr(live_map_config.settings, "warehouse_persist_raw_lidar_layer", True)
    assert live_map_config.should_persist_raw_lidar_chunks() is True


def test_should_not_persist_raw_lidar_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(live_map_config.settings, "warehouse_live_map_raw_lidar_enabled", False)
    monkeypatch.setattr(live_map_config.settings, "warehouse_include_raw_lidar_preview", False)
    monkeypatch.setattr(live_map_config.settings, "warehouse_persist_raw_lidar_layer", False)
    assert live_map_config.should_persist_raw_lidar_chunks() is False
