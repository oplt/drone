from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from time import monotonic
from typing import Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from backend.core.config.runtime import settings
from backend.core.database.session import get_db
from backend.modules.agriculture.models import (
    AgricultureFlight,
    AgricultureTelemetryReceipt,
)
from backend.modules.agriculture.schemas import (
    AgricultureTelemetryOut,
    LiveAdvisoryOut,
    TelemetryBatchIn,
)
from backend.modules.agriculture.service import agriculture_service
from backend.modules.agriculture.live import LiveFrame
from backend.modules.identity.dependencies import OrgUser, require_mission_exec, require_org_user
from backend.observability.instruments import observed_span
from backend.modules.agriculture.runtime_service import append_event, replay_events
from backend.modules.missions.api.routes import _apply_mission_command, _get_runtime_for_user
from backend.modules.vehicle_runtime.factory import get_orchestrator
from backend.infrastructure.runtime.blocking import run_blocking

from backend.modules.agriculture.routers import common as _common
from backend.modules.agriculture.routers.common import (
    AGRICULTURE_SCHEMA_VERSION,
    agriculture_rate_limit,
    require_owned_flight,
)

router = APIRouter()


def _telemetry_payload_checksum(payload: TelemetryBatchIn) -> str:
    return hashlib.sha256(payload.model_dump_json().encode()).hexdigest()


async def _get_telemetry_receipt(
    db: AsyncSession,
    *,
    flight_id: str,
    idempotency_key: str,
) -> tuple[str, dict] | None:
    row = await db.scalar(
        select(AgricultureTelemetryReceipt).where(
            AgricultureTelemetryReceipt.flight_id == flight_id,
            AgricultureTelemetryReceipt.idempotency_key == idempotency_key,
        )
    )
    if row is not None:
        return row.payload_checksum, dict(row.result_json or {})
    return None


def _legacy_manifest_receipt(
    flight: AgricultureFlight,
    idempotency_key: str,
) -> tuple[str, dict] | None:
    receipt = dict((flight.input_manifest or {}).get("telemetry_batch_receipts", {})).get(
        idempotency_key
    )
    if not isinstance(receipt, dict):
        return None
    checksum = receipt.get("checksum")
    result = receipt.get("result")
    if not isinstance(checksum, str) or not isinstance(result, dict):
        return None
    return checksum, result


def _telemetry_idempotency_conflict(checksum: str, payload_checksum: str) -> None:
    if checksum != payload_checksum:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IDEMPOTENCY_KEY_REUSED",
                "message": "Idempotency-Key was already used with another payload",
            },
        )


class AgricultureRuntimeCommandIn(BaseModel):
    command_id: str = Field(..., min_length=8, max_length=128)
    command: Literal["pause", "resume", "abort", "rth", "land"]
    reason: str | None = Field(default=None, max_length=500)
    expected_sequence: int | None = Field(default=None, ge=0)


class AgricultureRuntimeCommandOut(BaseModel):
    schema_version: str = AGRICULTURE_SCHEMA_VERSION
    flight_id: str
    command_id: str
    command: str
    accepted: bool
    state_before: str
    state_after: str
    message: str
    sequence: int
    duplicate: bool = False


@router.get("/flights/{flight_id}/runtime/events")
async def get_agriculture_runtime_events(
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=400),
    db: AsyncSession = Depends(get_db),
    flight: AgricultureFlight = Depends(require_owned_flight),
):
    replay = await replay_events(db, flight_id=flight.id, after_sequence=after_sequence, limit=limit)
    return {
        "schema_version": AGRICULTURE_SCHEMA_VERSION,
        "flight_id": flight.id,
        "events": [
            {"schema_version": "agriculture.runtime.v1", "sequence": row.sequence, "type": "agriculture_runtime_event", "event_type": row.event_type, "severity": row.severity, "state": row.state, "payload": row.payload, "source": row.source, "occurred_at": row.occurred_at}
            for row in replay["events"]
        ],
        "next_sequence": replay["next_sequence"],
        "latest_sequence": replay["latest_sequence"],
        "has_more": replay["has_more"],
        "gap_detected": replay["gap_detected"],
    }


@router.post("/flights/{flight_id}/runtime/commands", response_model=AgricultureRuntimeCommandOut)
async def issue_agriculture_runtime_command(
    flight_id: str,
    payload: AgricultureRuntimeCommandIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
):
    flight = await _common._owned_flight(flight_id, org_user, db)
    if payload.expected_sequence is not None:
        latest = await replay_events(db, flight_id=flight.id, after_sequence=0, limit=1)
        if payload.expected_sequence != latest["latest_sequence"]:
            raise HTTPException(status_code=409, detail={"code": "STALE_RUNTIME_CURSOR", "latest_sequence": latest["latest_sequence"], "message": "Refresh runtime events before issuing a safety command."})
    runtime = await _get_runtime_for_user(flight.mission_id, user_id=int(org_user.user.id))
    orchestrator = await get_orchestrator()
    try:
        result = await _apply_mission_command(
            orch=orchestrator,
            runtime=runtime,
            command=payload.command,
            idempotency_key=payload.command_id,
            requested_by_user_id=int(org_user.user.id),
            reason=payload.reason,
        )
    except ValueError as exc:
        from backend.observability import prometheus_metrics
        prometheus_metrics.agriculture_runtime_command_failures_total.labels(command=payload.command, reason="invalid_transition").inc()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    from backend.observability import prometheus_metrics
    prometheus_metrics.agriculture_runtime_commands_total.labels(command=payload.command, outcome="duplicate" if result.command_id != payload.command_id else ("accepted" if result.accepted else "rejected")).inc()
    event = await append_event(
        db,
        flight_id=flight.id,
        event_type="mission_command",
        state=result.state_after,
        severity="warning" if payload.command in {"abort", "rth", "land"} else "info",
        payload={"command_id": result.command_id, "command": result.command, "accepted": result.accepted, "duplicate": result.command_id != payload.command_id, "state_before": result.state_before, "state_after": result.state_after, "message": result.message, "reason": payload.reason},
        source="agriculture.runtime.command",
    )
    return AgricultureRuntimeCommandOut(
        flight_id=flight.id,
        command_id=result.command_id,
        command=result.command,
        accepted=result.accepted,
        state_before=result.state_before,
        state_after=result.state_after,
        message=result.message,
        sequence=event.sequence,
        duplicate=result.command_id != payload.command_id,
    )


@router.post("/flights/{flight_id}/telemetry", response_model=AgricultureTelemetryOut)
async def ingest_telemetry(
    flight_id: str,
    payload: TelemetryBatchIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=160),
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
):
    payload_checksum = _telemetry_payload_checksum(payload)
    flight = await _common._owned_flight(flight_id, org_user, db)

    cached = await _get_telemetry_receipt(
        db,
        flight_id=flight.id,
        idempotency_key=idempotency_key,
    )
    if cached is None:
        cached = _legacy_manifest_receipt(flight, idempotency_key)
    if cached is not None:
        _telemetry_idempotency_conflict(cached[0], payload_checksum)
        return AgricultureTelemetryOut(**cached[1])

    await _common.enforce_rate_limit(
        key=f"agriculture:telemetry:{org_user.user.id}:{flight_id}",
        limit=settings.agriculture_rate_telemetry_batches_per_window,
        window_seconds=settings.agriculture_rate_window_seconds,
    )

    flight = await db.scalar(
        select(AgricultureFlight).where(AgricultureFlight.id == flight.id).with_for_update()
    )
    if flight is None:
        raise HTTPException(status_code=404, detail="Agriculture flight not found")

    cached = await _get_telemetry_receipt(
        db,
        flight_id=flight.id,
        idempotency_key=idempotency_key,
    )
    if cached is None:
        cached = _legacy_manifest_receipt(flight, idempotency_key)
    if cached is not None:
        _telemetry_idempotency_conflict(cached[0], payload_checksum)
        return AgricultureTelemetryOut(**cached[1])

    with observed_span(
        "agriculture.telemetry_ingest",
        flight_id=flight.id,
        field_id=flight.field_id,
        mission_id=flight.mission_id,
    ):
        inserted, duplicates, rejected, gaps = await agriculture_service.ingest_telemetry(
            db, flight=flight, batch=payload
        )
    result = {
        "inserted": inserted,
        "duplicates": duplicates,
        "rejected": rejected,
        "gap_count": gaps,
    }
    db.add(
        AgricultureTelemetryReceipt(
            flight_id=flight.id,
            idempotency_key=idempotency_key,
            payload_checksum=payload_checksum,
            result_json=result,
        )
    )
    manifest = dict(flight.input_manifest or {})
    manifest["telemetry_samples"] = int(manifest.get("telemetry_samples", 0)) + inserted
    manifest["telemetry_last_ingested_at"] = datetime.now(UTC).isoformat()
    flight.input_manifest = manifest
    flight.coverage_summary = {**(flight.coverage_summary or {}), "telemetry_gap_count": gaps}
    await db.commit()
    if inserted or gaps:
        await append_event(
            db,
            flight_id=flight.id,
            event_type="telemetry_batch",
            severity="warning" if gaps else "info",
            payload={
                "inserted": inserted,
                "duplicates": duplicates,
                "rejected": rejected,
                "gap_count": gaps,
                "sample_count": len(payload.samples),
                "last_timestamp": payload.samples[-1].timestamp.isoformat(),
            },
            source="agriculture.runtime.telemetry",
        )
    return AgricultureTelemetryOut(**result)


@router.post(
    "/flights/{flight_id}/live/advisory",
    response_model=LiveAdvisoryOut,
    dependencies=[
        Depends(
            agriculture_rate_limit(
                "live",
                settings_limit="agriculture_rate_live_frames_per_window",
            )
        )
    ],
)
async def live_advisory(
    flight_id: str,
    frame: UploadFile = File(...),
    timestamp_seconds: float = Query(0.0, ge=0),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    _flight: AgricultureFlight = Depends(require_owned_flight),
):
    content = await frame.read()
    processor = _common.get_live_processor(flight_id)
    frame_index = int(timestamp_seconds * 30)
    geo = {"lat": lat, "lon": lon} if lat is not None and lon is not None else None

    def _process_live_frame():
        image = _common.decode_rgb_frame(content)
        processor.submit(LiveFrame(frame_index, timestamp_seconds, image, monotonic()))
        return processor.process_one(
            lambda current: _common.LiveAgricultureProcessor.rgb_advisory(
                current,
                frame_index=frame_index,
                timestamp_seconds=timestamp_seconds,
                geolocation=geo,
            )
        )

    try:
        advisory = await run_blocking(
            _process_live_frame,
            boundary="cpu",
            operation="agriculture_live_advisory",
            timeout_s=5.0,
        )
        if advisory is None:
            raise ValueError("live frame queue did not produce an advisory")
        return LiveAdvisoryOut(
            frame_index=advisory.frame_index,
            timestamp_seconds=advisory.timestamp_seconds,
            state=advisory.state,
            alerts=list(advisory.alerts),
            geolocation=advisory.geolocation,
            expires_at=advisory.expires_at,
            sampler_hz=processor.sampler_hz,
            dropped_frames=processor.dropped_frames,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

