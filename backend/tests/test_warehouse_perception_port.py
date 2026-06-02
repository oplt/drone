from __future__ import annotations

from typing import Any

import pytest

from backend.infrastructure.warehouse.perception import HttpWarehousePerceptionPort


class RecordingWarehousePort(HttpWarehousePerceptionPort):
    def __init__(self) -> None:
        super().__init__(
            bridge_url="http://bridge.test",
            websocket_url="ws://bridge.test",
            capture_root="/tmp/warehouse",
            profile="gazebo",
            timeout_s=1.0,
            deep_timeout_s=2.0,
        )
        self.paths: list[str] = []

    async def _get_json(self, path: str, *, timeout_s: float | None = None) -> dict[str, Any]:
        self.paths.append(path)
        return {
            "ready": False,
            "status": "blocked",
            "profile": "gazebo",
            "detail": "rgb_image_missing",
            "components": {
                "ros_graph": True,
                "missing_required_topics": ["rgb_image"],
            },
            "blockers": ["rgb_image_missing"],
            "retry_after_ms": 1000,
        }


@pytest.mark.asyncio
async def test_deep_status_uses_ready_endpoint() -> None:
    port = RecordingWarehousePort()

    status = await port.status(deep=True)

    assert port.paths == ["/ready"]
    assert status.reachable is True
    assert status.ready is False
    assert status.status == "blocked"
    assert status.components["missing_required_topics"] == ["rgb_image"]


@pytest.mark.asyncio
async def test_forced_deep_status_uses_forced_ready_endpoint() -> None:
    port = RecordingWarehousePort()

    await port.status(deep=True, force=True)

    assert port.paths == ["/ready?force=1"]
