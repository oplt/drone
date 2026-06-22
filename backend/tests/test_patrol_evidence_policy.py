from __future__ import annotations

from backend.modules.patrol.service.mission_runtime_store import ActiveMissionRuntimeContext
from backend.modules.patrol.vision.evidence_policy import (
    is_private_patrol_context,
    should_save_evidence_snapshot,
)


def test_is_private_patrol_context_with_task_type() -> None:
    ctx = ActiveMissionRuntimeContext(
        client_flight_id="f-1",
        mission_name="Patrol",
        mission_type="grid",
        state="running",
        db_flight_id=1,
        private_patrol_task_type="event_triggered_patrol",
        ai_tasks=("intruder_detection",),
    )
    assert is_private_patrol_context(ctx)


def test_is_private_patrol_context_with_mission_type() -> None:
    ctx = ActiveMissionRuntimeContext(
        client_flight_id="f-1",
        mission_name="Patrol",
        mission_type="perimeter_patrol",
        state="running",
        db_flight_id=1,
        private_patrol_task_type=None,
        ai_tasks=("intruder_detection",),
    )
    assert is_private_patrol_context(ctx)


def test_non_patrol_context() -> None:
    ctx = ActiveMissionRuntimeContext(
        client_flight_id="f-1",
        mission_name="Grid",
        mission_type="grid",
        state="running",
        db_flight_id=1,
        private_patrol_task_type=None,
        ai_tasks=(),
    )
    assert not is_private_patrol_context(ctx)
    assert not is_private_patrol_context(None)
