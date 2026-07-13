from __future__ import annotations

from typing import Any

from backend.modules.missions.audit_repository import mission_audit_repository
from backend.modules.missions.command_repository import operator_command_repo
from backend.modules.missions.repository import mission_runtime_repo
from backend.modules.preflight.repository import preflight_run_repo


class MissionRuntimeApplication:
    async def create(self, **values: Any):
        return await mission_runtime_repo.create(**values)

    async def get_by_client_id(self, client_flight_id: str):
        return await mission_runtime_repo.get_by_client_id(client_flight_id)

    async def get_by_client_id_for_user(self, client_flight_id: str, user_id: int):
        return await mission_runtime_repo.get_by_client_id_for_user(client_flight_id, user_id)

    async def get_active(self):
        return await mission_runtime_repo.get_active()

    async def list_recent(self, *, user_id: int | None, limit: int, offset: int = 0):
        return await mission_runtime_repo.list_recent(
            user_id=user_id, limit=limit, offset=offset
        )

    async def list_resumable(self, *, user_id: int | None, limit: int, offset: int = 0):
        return await mission_runtime_repo.list_resumable(
            user_id=user_id, limit=limit, offset=offset
        )

    async def set_state(self, client_flight_id: str, **values: Any) -> bool:
        return await mission_runtime_repo.set_state(client_flight_id, **values)

    async def finalize_execution(self, client_flight_id: str, **values: Any):
        return await mission_runtime_repo.finalize_execution(client_flight_id, **values)

    async def set_flight_id(self, client_flight_id: str, *, flight_id: int) -> None:
        await mission_runtime_repo.set_flight_id(client_flight_id, flight_id=flight_id)

    async def get_idempotency_result(self, client_flight_id: str, key: str):
        return await mission_runtime_repo.get_idempotency_result(client_flight_id, key)

    async def apply_command(self, client_flight_id: str, **values: Any):
        return await mission_runtime_repo.apply_command(client_flight_id, **values)

    async def record_command(self, **values: Any):
        return await operator_command_repo.create(**values)

    async def list_commands(self, client_flight_id: str, *, limit: int = 400, offset: int = 0):
        return await operator_command_repo.list_for_mission(
            client_flight_id, limit=limit, offset=offset
        )

    async def create_preflight(self, **values: Any):
        return await preflight_run_repo.create(**values)

    async def get_preflight(self, run_uuid: str):
        return await preflight_run_repo.get_by_uuid(run_uuid)

    async def list_events(self, *, flight_id: int, limit: int, offset: int = 0):
        return await mission_audit_repository.list_events(
            flight_id=flight_id, limit=limit, offset=offset
        )

    async def set_operational_flight_status(
        self, repository: Any, flight_id: int, *, status: Any, note: str
    ) -> bool:
        return await repository.set_flight_status_if_active(flight_id, status=status, note=note)

    async def finish_operational_flight(
        self, repository: Any, flight_id: int, *, status: Any, note: str
    ) -> bool:
        return await repository.finish_flight_if_in_progress(flight_id, status=status, note=note)


mission_application = MissionRuntimeApplication()
