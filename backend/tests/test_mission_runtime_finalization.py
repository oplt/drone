import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.modules.missions.repository import MissionRuntimeRepository


def _repository_with_row(row):
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    return MissionRuntimeRepository(session_factory=lambda: context), session


def test_finalize_execution_updates_active_runtime_atomically() -> None:
    row = SimpleNamespace(
        state="airborne",
        failure_reason=None,
        updated_at=None,
        ended_at=None,
    )
    repository, session = _repository_with_row(row)

    result = asyncio.run(
        repository.finalize_execution("flight-1", state="failed", error="motor fault")
    )

    assert result is row
    assert row.state == "failed"
    assert row.failure_reason == "motor fault"
    assert row.ended_at is not None
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(row)


def test_finalize_execution_preserves_concurrent_terminal_state() -> None:
    row = SimpleNamespace(
        state="aborted",
        failure_reason="operator abort",
        updated_at=None,
        ended_at=object(),
    )
    repository, session = _repository_with_row(row)

    result = asyncio.run(
        repository.finalize_execution("flight-1", state="completed")
    )

    assert result is row
    assert row.state == "aborted"
    assert row.failure_reason == "operator abort"
    session.commit.assert_not_awaited()
    session.refresh.assert_not_awaited()


def test_execute_mission_uses_one_authoritative_finalizer(monkeypatch) -> None:
    from backend.modules.missions.api import routes

    mission = MagicMock()
    mission.execute = AsyncMock()
    set_runtime_state = AsyncMock()
    finalize_execution = AsyncMock(return_value=None)
    legacy_get = AsyncMock()
    monkeypatch.setattr(routes, "_set_runtime_state", set_runtime_state)
    monkeypatch.setattr(
        routes.mission_application,
        "finalize_execution",
        finalize_execution,
    )
    monkeypatch.setattr(routes.mission_application, "get_by_client_id", legacy_get)
    orchestrator = SimpleNamespace(current_client_flight_id=None)

    asyncio.run(
        routes.execute_mission(
            orchestrator,
            mission,
            cruise_alt=12.0,
            mission_name="Inspection",
            runtime_id="flight-1",
        )
    )

    set_runtime_state.assert_awaited_once_with("flight-1", state="airborne")
    finalize_execution.assert_awaited_once_with(
        "flight-1",
        state="completed",
        error=None,
    )
    legacy_get.assert_not_awaited()
