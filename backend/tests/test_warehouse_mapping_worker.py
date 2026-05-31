from __future__ import annotations

from unittest import mock

from backend.entrypoints.workers import warehouse_mapping_tasks
from backend.modules.warehouse.service.mapping import WarehouseScanMappingPreconditionError


def test_mapping_worker_does_not_retry_precondition_failure() -> None:
    task = warehouse_mapping_tasks.process_warehouse_mapping_job
    with mock.patch.object(
        warehouse_mapping_tasks,
        "_run_on_worker_loop",
        side_effect=WarehouseScanMappingPreconditionError("no artifacts"),
    ):
        result = task.run(job_id=42)  # type: ignore[attr-defined]
    assert result["status"] == "failed_precondition"
    assert "no artifacts" in result["error"]
