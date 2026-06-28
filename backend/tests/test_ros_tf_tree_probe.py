from __future__ import annotations

import pytest

from backend.modules.warehouse.service.ros_tf_tree_probe import probe_warehouse_ros_tf_tree


@pytest.mark.asyncio
async def test_probe_warehouse_ros_tf_tree_aggregates_edge_results(monkeypatch) -> None:
    async def _fake_edge(parent: str, child: str, **kwargs):
        return {
            "parent_frame": parent,
            "child_frame": child,
            "tf_ok": parent != "base_link" or child != "gimbal_link",
            "detail": None if child != "gimbal_link" else "missing",
        }

    monkeypatch.setattr(
        "backend.modules.warehouse.service.ros_tf_tree_probe.probe_ros_tf_edge",
        _fake_edge,
    )
    result = await probe_warehouse_ros_tf_tree(
        edges=frozenset(
            {
                ("warehouse_map", "odom"),
                ("odom", "base_link"),
                ("base_link", "gimbal_link"),
            }
        )
    )
    assert result["edge_count"] == 3
    assert result["ok_count"] == 2
    assert result["tf_ok"] is False
    assert result["missing_edges"] == ["base_link->gimbal_link"]
    assert len(result["edges"]) == 3


@pytest.mark.asyncio
async def test_probe_ros_tf_edge_parses_tf2_echo_success(monkeypatch) -> None:
    from backend.modules.warehouse.service import ros_tf_tree_probe

    class _Result:
        stdout = "At time 123.4\n- Translation: [0.0, 0.0, 0.0]\n"
        stderr = ""

    def _fake_run(*args, **kwargs):
        return _Result()

    monkeypatch.setattr(ros_tf_tree_probe.asyncio, "to_thread", lambda fn, *a, **k: fn(*a, **k))
    monkeypatch.setattr(ros_tf_tree_probe.subprocess, "run", _fake_run)

    edge = await ros_tf_tree_probe.probe_ros_tf_edge("odom", "base_link")
    assert edge["tf_ok"] is True
    assert edge["parent_frame"] == "odom"
    assert edge["child_frame"] == "base_link"
