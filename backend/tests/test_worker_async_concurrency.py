from __future__ import annotations

import pytest

from backend.entrypoints.workers.agents_tasks import run_agent_task
from backend.entrypoints.workers.celery_app import (
    CELERY_DEFAULT_TASK_SOFT_TIME_LIMIT_SECONDS,
    CELERY_DEFAULT_TASK_TIME_LIMIT_SECONDS,
    CELERY_PHOTOGRAMMETRY_SOFT_TIME_LIMIT_SECONDS,
    CELERY_PHOTOGRAMMETRY_TIME_LIMIT_SECONDS,
    celery_app,
)
from backend.entrypoints.workers.irrigation_tasks import process_irrigation_job
from backend.entrypoints.workers.warehouse_mapping_tasks import (
    _extraction_idempotency_key,
    extract_warehouse_structure,
)
from backend.modules.agents.schemas import AgentContext, AgentPhase
from backend.shared.worker_idempotency import WorkerTaskClaim, claim_worker_task


def test_celery_global_time_limit_is_conservative() -> None:
    assert celery_app.conf.task_time_limit == CELERY_DEFAULT_TASK_TIME_LIMIT_SECONDS
    assert CELERY_DEFAULT_TASK_TIME_LIMIT_SECONDS <= 30 * 60
    assert CELERY_PHOTOGRAMMETRY_TIME_LIMIT_SECONDS == 6 * 60 * 60
    photo = celery_app.conf.task_annotations["photogrammetry.process_job"]
    assert photo["time_limit"] == CELERY_PHOTOGRAMMETRY_TIME_LIMIT_SECONDS
    assert photo["time_limit"] > celery_app.conf.task_time_limit


def test_celery_soft_time_limit_is_below_hard_limit() -> None:
    assert celery_app.conf.task_soft_time_limit == CELERY_DEFAULT_TASK_SOFT_TIME_LIMIT_SECONDS
    assert celery_app.conf.task_soft_time_limit < celery_app.conf.task_time_limit
    photo = celery_app.conf.task_annotations["photogrammetry.process_job"]
    assert photo["soft_time_limit"] == CELERY_PHOTOGRAMMETRY_SOFT_TIME_LIMIT_SECONDS
    assert photo["soft_time_limit"] < photo["time_limit"]


def test_bound_worker_tasks_have_explicit_soft_limits() -> None:
    assert run_agent_task.soft_time_limit == 540
    assert run_agent_task.time_limit == 600
    assert run_agent_task.soft_time_limit < run_agent_task.time_limit
    assert process_irrigation_job.soft_time_limit == 1500
    assert process_irrigation_job.time_limit == 1800
    assert extract_warehouse_structure.soft_time_limit == 3300
    assert extract_warehouse_structure.time_limit == 3600


def test_worker_idempotency_claim_skips_duplicate_enqueue(monkeypatch) -> None:
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, key: str) -> str | None:
            return store.get(key)

        def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
            if nx and key in store:
                return False
            store[key] = value
            return True

        def setex(self, key: str, ttl: int, value: str) -> None:
            store[key] = value

        def delete(self, key: str) -> None:
            store.pop(key, None)

    monkeypatch.setattr(
        "backend.shared.worker_idempotency.get_sync_redis_client",
        lambda: FakeRedis(),
    )

    first_claim, _ = claim_worker_task("agents", "idem-1", ttl_s=60)
    second_claim, _ = claim_worker_task("agents", "idem-1", ttl_s=60)

    assert first_claim == WorkerTaskClaim.EXECUTE
    assert second_claim == WorkerTaskClaim.SKIP_IN_FLIGHT


def test_run_agent_task_returns_duplicate_without_side_effect(monkeypatch) -> None:
    execute_calls: list[tuple[str, AgentContext]] = []

    async def fake_execute(agent_id, context):
        execute_calls.append((agent_id.value, context))
        return {"status": "ok", "text": "done"}

    monkeypatch.setattr(
        "backend.entrypoints.workers.agents_tasks.execute_agent",
        fake_execute,
    )
    monkeypatch.setattr(
        "backend.entrypoints.workers.agents_tasks.claim_worker_task",
        lambda *_args, **_kwargs: (WorkerTaskClaim.SKIP_IN_FLIGHT, None),
    )

    context = AgentContext(
        phase=AgentPhase.ON_DEMAND,
        idempotency_key="agent-run-dedupe-test",
    ).model_dump(mode="json")
    result = run_agent_task.run(agent_id="assistant", context=context)

    assert result == {"status": "duplicate", "idempotency_key": "agent-run-dedupe-test"}
    assert execute_calls == []


def test_warehouse_extraction_idempotency_key_prefers_job_id() -> None:
    assert (
        _extraction_idempotency_key(
            warehouse_map_id=7,
            model_id=3,
            extraction_job_id=99,
        )
        == "job:99"
    )
    assert (
        _extraction_idempotency_key(
            warehouse_map_id=7,
            model_id=3,
            extraction_job_id=None,
        )
        == "map:7:model:3"
    )


def test_extract_warehouse_structure_uses_worker_loop_run(monkeypatch) -> None:
    from backend.entrypoints.workers import warehouse_mapping_tasks

    run_calls: list[object] = []

    def tracking_run(coro):
        run_calls.append(coro)
        coro.close()
        return {"status": "ready", "target_count": 0}

    monkeypatch.setattr(warehouse_mapping_tasks._worker_loop, "run", tracking_run)
    monkeypatch.setattr(
        "backend.entrypoints.workers.warehouse_mapping_tasks.claim_worker_task",
        lambda *_args, **_kwargs: (WorkerTaskClaim.EXECUTE, None),
    )
    monkeypatch.setattr(
        "backend.entrypoints.workers.warehouse_mapping_tasks.complete_worker_task",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "backend.entrypoints.workers.warehouse_mapping_tasks.get_extraction_state",
        lambda _map_id: None,
    )

    result = extract_warehouse_structure.run(
        warehouse_map_id=1,
        model_id=2,
        client_flight_id="flight-1",
    )

    assert result == {"status": "ready", "target_count": 0}
    assert len(run_calls) == 1
