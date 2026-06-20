from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

from backend.modules.warehouse.service.preflight_cache import clear_preflight_snapshot_cache

logger = logging.getLogger(__name__)

_PREFLIGHT_RUNS: OrderedDict[str, Any] = OrderedDict()
_PREFLIGHT_RUNS_MAX = 50
_PREFLIGHT_RUNS_TTL_S = 60 * 60
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def remember_preflight_run(run: Any) -> None:
    now = datetime.now(UTC)
    _PREFLIGHT_RUNS[run.run_id] = run
    _PREFLIGHT_RUNS.move_to_end(run.run_id)
    stale_keys = [
        key
        for key, value in _PREFLIGHT_RUNS.items()
        if (now - value.started_at).total_seconds() > _PREFLIGHT_RUNS_TTL_S
    ]
    for key in stale_keys:
        _PREFLIGHT_RUNS.pop(key, None)
    while len(_PREFLIGHT_RUNS) > _PREFLIGHT_RUNS_MAX:
        _PREFLIGHT_RUNS.popitem(last=False)


def get_preflight_run(run_id: str) -> Any | None:
    return _PREFLIGHT_RUNS.get(run_id)


def _record_refresh_metrics(run: Any) -> None:
    try:
        from backend.observability.prometheus_metrics import (
            preflight_runs_total,
            warehouse_preflight_refresh_duration_seconds,
            warehouse_preflight_refresh_total,
        )

        overall = "ready" if run.snapshot and run.snapshot.ready_to_fly else "blocked"
        preflight_runs_total.labels(overall_status=overall).inc()
        warehouse_preflight_refresh_total.labels(
            status=run.status,
            deep=str(run.deep).lower(),
            force=str(run.force).lower(),
        ).inc()
        if run.finished_at is not None:
            duration = max(0.0, (run.finished_at - run.started_at).total_seconds())
            warehouse_preflight_refresh_duration_seconds.labels(
                deep=str(run.deep).lower(),
                force=str(run.force).lower(),
            ).observe(duration)
    except Exception:
        logger.debug("Failed to record background preflight metrics", exc_info=True)


async def _run_preflight_refresh(
    *,
    run_id: str,
    build_snapshot,
    connect_drone,
    start_mapping_stack,
    db_factory,
    user: Any,
    mission_loaded: bool,
) -> None:
    """Complete one expensive refresh outside the initiating HTTP request."""
    run = _PREFLIGHT_RUNS.get(run_id)
    if run is None or run.finished_at is not None:
        return
    try:
        drone_connected, drone_connect_error = await connect_drone()
        async with db_factory() as db:
            snapshot = await build_snapshot(
                db,
                user=user,
                deep=True,
                force=True,
                mission_loaded=mission_loaded,
                start_bridge=True,
            )
        if drone_connected and snapshot.ready_to_fly and snapshot.nvblox_ok is not True:
            try:
                await start_mapping_stack()
            except Exception as exc:
                logger.warning(
                    "Background preflight could not start nvblox run_id=%s: %s",
                    run_id,
                    exc,
                    exc_info=True,
                )
        if not drone_connected and drone_connect_error:
            blockers = list(snapshot.blockers)
            if drone_connect_error not in blockers:
                blockers.insert(0, drone_connect_error)
            snapshot = snapshot.model_copy(
                update={
                    "ready": False,
                    "ready_to_fly": False,
                    "blocking": True,
                    "primary_blocker": blockers[0],
                    "blockers": blockers,
                    "blocking_reasons": blockers,
                    "suggested_actions": blockers[:3],
                    "last_error": drone_connect_error,
                }
            )
        run.snapshot = snapshot
        run.status = "complete"
        run.finished_at = datetime.now(UTC)
        remember_preflight_run(run)
    except asyncio.CancelledError:
        run.status = "failed"
        run.error = "Preflight refresh was cancelled"
        run.finished_at = datetime.now(UTC)
        remember_preflight_run(run)
        raise
    except Exception as exc:
        logger.exception("Background preflight refresh failed run_id=%s", run_id)
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = datetime.now(UTC)
        remember_preflight_run(run)
    finally:
        await clear_preflight_snapshot_cache()
        _record_refresh_metrics(run)


def schedule_preflight_refresh(
    *,
    run_id: str,
    build_snapshot,
    connect_drone,
    start_mapping_stack,
    db_factory,
    user: Any,
    mission_loaded: bool,
) -> None:
    task = asyncio.create_task(
        _run_preflight_refresh(
            run_id=run_id,
            build_snapshot=build_snapshot,
            connect_drone=connect_drone,
            start_mapping_stack=start_mapping_stack,
            db_factory=db_factory,
            user=user,
            mission_loaded=mission_loaded,
        )
    )
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
