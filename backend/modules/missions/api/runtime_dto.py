"""Mission runtime DTOs and command API schemas shared by route modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.modules.missions.application import mission_application
from backend.modules.missions.domain.state_machine import MissionLifecycleState

MissionCommand = Literal["pause", "resume", "abort", "rth", "land"]


class MissionCommandIn(BaseModel):
    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="Idempotency key. Can also be provided via Idempotency-Key header.",
    )
    reason: str | None = Field(default=None, max_length=240)


class MissionCommandOut(BaseModel):
    flight_id: str
    command_id: str
    command: str
    idempotency_key: str
    state_before: str
    state_after: str
    accepted: bool
    message: str
    requested_at: float


class MissionCommandAuditOut(BaseModel):
    command_id: str
    command: str
    idempotency_key: str
    requested_by_user_id: int
    requested_at: float
    state_before: str
    state_after: str
    accepted: bool
    message: str
    reason: str | None = None


@dataclass
class MissionCommandAuditRecord:
    command_id: str
    command: MissionCommand
    idempotency_key: str
    requested_by_user_id: int
    requested_at: float
    state_before: MissionLifecycleState
    state_after: MissionLifecycleState
    accepted: bool
    message: str
    reason: str | None = None


@dataclass
class MissionRuntimeRecord:
    client_flight_id: str
    user_id: int
    mission_name: str
    mission_type: str
    mission_task_type: str | None
    private_patrol_task_type: str | None
    preflight_run_id: str | None
    state: MissionLifecycleState
    created_at: float
    updated_at: float
    db_flight_id: int | None = None
    last_error: str | None = None
    private_patrol_trigger_type: str | None = None
    private_patrol_target_label: str | None = None
    command_audit: list[MissionCommandAuditRecord] = field(default_factory=list)
    idempotency_results: dict[str, dict] = field(default_factory=dict)
    private_patrol_ai_tasks: list[str] = field(default_factory=list)

    @classmethod
    def from_db(cls, row: Any) -> MissionRuntimeRecord:
        created_ts = (
            row.created_at.timestamp()
            if isinstance(row.created_at, datetime)
            else float(row.created_at or 0)
        )
        updated_ts = (
            row.updated_at.timestamp() if isinstance(row.updated_at, datetime) else created_ts
        )
        audit_records = [
            MissionCommandAuditRecord(
                command_id=e.get("command_id", ""),
                command=e.get("command", ""),
                idempotency_key=e.get("idempotency_key", ""),
                requested_by_user_id=int(e.get("requested_by_user_id", 0)),
                requested_at=float(e.get("requested_at", 0)),
                state_before=e.get("state_before", ""),
                state_after=e.get("state_after", ""),
                accepted=bool(e.get("accepted", False)),
                message=e.get("message", ""),
                reason=e.get("reason"),
            )
            for e in (row.command_audit or [])
        ]
        return cls(
            client_flight_id=row.client_flight_id,
            user_id=row.user_id or 0,
            mission_name=row.mission_name,
            mission_type=row.mission_type,
            mission_task_type=row.mission_task_type,
            private_patrol_task_type=row.private_patrol_task_type,
            preflight_run_id=row.preflight_run_uuid,
            state=row.state,
            created_at=created_ts,
            updated_at=updated_ts,
            db_flight_id=row.flight_id,
            last_error=row.failure_reason,
            command_audit=audit_records,
            idempotency_results=dict(row.idempotency_results or {}),
            private_patrol_ai_tasks=list(row.ai_tasks or []),
        )


async def get_runtime_for_user(
    flight_id: str,
    *,
    user_id: int,
) -> MissionRuntimeRecord:
    db_row = await mission_application.get_by_client_id_for_user(flight_id, user_id)
    if db_row is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return MissionRuntimeRecord.from_db(db_row)


def resolve_idempotency_key(
    payload_key: str | None,
    header_key: str | None,
) -> str:
    payload = (payload_key or "").strip()
    header = (header_key or "").strip()
    if payload and header and payload != header:
        raise HTTPException(
            status_code=409,
            detail="Idempotency key mismatch between body and Idempotency-Key header.",
        )

    key = payload or header
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency key required (body.idempotency_key or Idempotency-Key header).",
        )
    if len(key) < 8 or len(key) > 128:
        raise HTTPException(status_code=400, detail="Invalid idempotency key length")
    return key
