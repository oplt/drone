import asyncio
from datetime import UTC, datetime

from backend.modules.warehouse.http_models import (
    WarehousePreflightOut,
    WarehousePreflightRefreshOut,
)
from backend.modules.warehouse.service import preflight_background


class _DatabaseContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def test_background_preflight_is_passive_and_completes_once(monkeypatch) -> None:
    preflight_background._PREFLIGHT_RUNS.clear()
    run = WarehousePreflightRefreshOut(
        run_id="run-1",
        status="running",
        deep=True,
        force=True,
        mission_loaded=False,
        started_at=datetime.now(UTC),
    )
    preflight_background.remember_preflight_run(run)
    calls = {"connect": 0, "snapshot": 0, "stack": 0}

    async def connect_drone():
        calls["connect"] += 1
        return True, None

    async def build_snapshot(*args, **kwargs):
        calls["snapshot"] += 1
        assert kwargs["start_bridge"] is False
        return WarehousePreflightOut(
            ready=True,
            blocking=False,
            ready_to_fly=True,
            nvblox_ok=False,
            blockers=[],
            blocking_reasons=[],
        )

    async def start_mapping_stack():
        calls["stack"] += 1

    async def clear_cache():
        return None

    monkeypatch.setattr(preflight_background, "clear_preflight_snapshot_cache", clear_cache)
    monkeypatch.setattr(preflight_background, "_record_refresh_metrics", lambda run: None)

    asyncio.run(
        preflight_background._run_preflight_refresh(
            run_id=run.run_id,
            build_snapshot=build_snapshot,
            connect_drone=connect_drone,
            start_mapping_stack=start_mapping_stack,
            db_factory=_DatabaseContext,
            user=object(),
            mission_loaded=False,
        )
    )

    completed = preflight_background.get_preflight_run(run.run_id)
    assert completed is not None
    assert completed.status == "complete"
    assert completed.finished_at is not None
    assert completed.snapshot is not None
    assert calls == {"connect": 0, "snapshot": 1, "stack": 0}


def test_background_preflight_marks_probe_failure_terminal(monkeypatch) -> None:
    preflight_background._PREFLIGHT_RUNS.clear()
    run = WarehousePreflightRefreshOut(
        run_id="run-failed",
        status="running",
        deep=True,
        force=True,
        mission_loaded=False,
        started_at=datetime.now(UTC),
    )
    preflight_background.remember_preflight_run(run)

    async def connect_drone():
        return True, None

    async def build_snapshot(*args, **kwargs):
        raise RuntimeError("probe unavailable")

    async def start_mapping_stack():
        return None

    async def clear_cache():
        return None

    monkeypatch.setattr(preflight_background, "clear_preflight_snapshot_cache", clear_cache)
    monkeypatch.setattr(preflight_background, "_record_refresh_metrics", lambda run: None)

    asyncio.run(
        preflight_background._run_preflight_refresh(
            run_id=run.run_id,
            build_snapshot=build_snapshot,
            connect_drone=connect_drone,
            start_mapping_stack=start_mapping_stack,
            db_factory=_DatabaseContext,
            user=object(),
            mission_loaded=False,
        )
    )

    failed = preflight_background.get_preflight_run(run.run_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "probe unavailable"
    assert failed.finished_at is not None
