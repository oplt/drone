import asyncio

from backend.modules.preflight.checks.schemas import CheckStatus, PreflightReport
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service import warehouse_preflight


def test_ros_preflight_reuses_supplied_perception_probe(monkeypatch) -> None:
    status = WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        components={"local_position_ok": True},
    )
    report = PreflightReport(
        mission_type="warehouse_scan",
        overall_status=CheckStatus.PASS,
        base_checks=[],
        mission_checks=[],
    )

    async def unexpected_probe(**kwargs):
        raise AssertionError("perception was probed twice")

    class FakeOrchestrator:
        def __init__(self, *, config):
            self.config = config

        async def run(self, *args, **kwargs):
            return report

    monkeypatch.setattr(
        warehouse_preflight,
        "fetch_warehouse_perception_status",
        unexpected_probe,
    )
    monkeypatch.setattr(warehouse_preflight, "PreflightOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(warehouse_preflight, "_warm_mapping_stack_in_background", lambda: None)

    result = asyncio.run(
        warehouse_preflight.run_warehouse_ros_preflight_report(
            warehouse_preflight.default_warehouse_scan_preflight_mission_data(),
            cruise_alt=2.0,
            perception_status=status,
            force=True,
            source="test",
        )
    )

    assert result is report
