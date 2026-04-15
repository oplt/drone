"""Compliance record endpoints for mission runtimes.

Prefix  : /missions  (mounted under /tasks in api_main.py)
Auth    : require_user — missions are keyed by client_flight_id, not org_id directly.
Models  : ComplianceRecord, MissionRuntime, PreflightRun, FlightEvent
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from backend.auth.deps import require_user
from backend.db.models import (
    ComplianceRecord,
    FlightEvent,
    MissionRuntime,
    PreflightRun,
)
from backend.db.session import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/missions", tags=["compliance"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ComplianceUpsert(BaseModel):
    remote_id_status: str = "unknown"  # broadcast | off | unknown
    laanc_auth_number: str | None = None
    laanc_auth_expires: datetime | None = None
    notes: str | None = None


class CompliancePatch(BaseModel):
    remote_id_status: str | None = None
    laanc_auth_number: str | None = None
    laanc_auth_expires: datetime | None = None
    notes: str | None = None


class ComplianceOut(BaseModel):
    id: int
    remote_id_status: str
    laanc_auth_number: str | None
    laanc_auth_expires: datetime | None
    preflight_ack_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_runtime(flight_id: str, db) -> MissionRuntime:
    q = await db.execute(
        select(MissionRuntime).where(MissionRuntime.client_flight_id == flight_id)
    )
    runtime = q.scalar_one_or_none()
    if not runtime:
        raise HTTPException(status_code=404, detail="Mission not found")
    return runtime


def _compliance_out(c: ComplianceRecord) -> ComplianceOut:
    return ComplianceOut(
        id=c.id,
        remote_id_status=c.remote_id_status,
        laanc_auth_number=c.laanc_auth_number,
        laanc_auth_expires=c.laanc_auth_expires,
        preflight_ack_at=c.preflight_ack_at,
        notes=c.notes,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def _resolve_preflight_ack(runtime: MissionRuntime, db) -> datetime | None:
    """Return completed_at from linked PreflightRun if available."""
    if not runtime.preflight_run_id:
        return None
    q = await db.execute(
        select(PreflightRun.completed_at).where(
            PreflightRun.id == runtime.preflight_run_id
        )
    )
    return q.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/{flight_id}/compliance", response_model=ComplianceOut, status_code=201)
async def upsert_compliance(
    flight_id: str,
    payload: ComplianceUpsert,
    _user=Depends(require_user),
) -> ComplianceOut:
    """Create or fully replace the compliance record for a mission."""
    async with Session() as db:
        runtime = await _get_runtime(flight_id, db)

        # Find existing record (unique per mission_runtime_id)
        q = await db.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.mission_runtime_id == runtime.id
            )
        )
        record = q.scalar_one_or_none()

        preflight_ack_at = await _resolve_preflight_ack(runtime, db)

        if record is None:
            record = ComplianceRecord(
                org_id=runtime.org_id,
                mission_runtime_id=runtime.id,
                remote_id_status=payload.remote_id_status,
                laanc_auth_number=payload.laanc_auth_number,
                laanc_auth_expires=payload.laanc_auth_expires,
                preflight_ack_at=preflight_ack_at,
                notes=payload.notes,
            )
            db.add(record)
        else:
            record.remote_id_status = payload.remote_id_status
            record.laanc_auth_number = payload.laanc_auth_number
            record.laanc_auth_expires = payload.laanc_auth_expires
            record.notes = payload.notes
            # Only backfill preflight_ack_at if not already set
            if record.preflight_ack_at is None and preflight_ack_at is not None:
                record.preflight_ack_at = preflight_ack_at

        await db.commit()
        await db.refresh(record)
        return _compliance_out(record)


@router.get("/{flight_id}/compliance", response_model=ComplianceOut)
async def get_compliance(
    flight_id: str,
    _user=Depends(require_user),
) -> ComplianceOut:
    """Fetch the compliance record for a mission. 404 if none exists."""
    async with Session() as db:
        runtime = await _get_runtime(flight_id, db)
        q = await db.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.mission_runtime_id == runtime.id
            )
        )
        record = q.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="No compliance record for this mission")
        return _compliance_out(record)


@router.patch("/{flight_id}/compliance", response_model=ComplianceOut)
async def patch_compliance(
    flight_id: str,
    payload: CompliancePatch,
    _user=Depends(require_user),
) -> ComplianceOut:
    """Partially update the compliance record for a mission."""
    async with Session() as db:
        runtime = await _get_runtime(flight_id, db)
        q = await db.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.mission_runtime_id == runtime.id
            )
        )
        record = q.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="No compliance record for this mission")

        if payload.remote_id_status is not None:
            record.remote_id_status = payload.remote_id_status
        if payload.laanc_auth_number is not None:
            record.laanc_auth_number = payload.laanc_auth_number
        if payload.laanc_auth_expires is not None:
            record.laanc_auth_expires = payload.laanc_auth_expires
        if payload.notes is not None:
            record.notes = payload.notes

        await db.commit()
        await db.refresh(record)
        return _compliance_out(record)


@router.get("/{flight_id}/compliance/summary")
async def compliance_summary(
    flight_id: str,
    _user=Depends(require_user),
) -> dict[str, Any]:
    """Return a full compliance bundle: mission meta, compliance record, preflight, event counts."""
    async with Session() as db:
        runtime = await _get_runtime(flight_id, db)

        # Compliance record (may be None)
        q = await db.execute(
            select(ComplianceRecord).where(
                ComplianceRecord.mission_runtime_id == runtime.id
            )
        )
        comp = q.scalar_one_or_none()

        # Preflight run (may be None)
        preflight_data: dict | None = None
        if runtime.preflight_run_id:
            q2 = await db.execute(
                select(PreflightRun).where(PreflightRun.id == runtime.preflight_run_id)
            )
            pf = q2.scalar_one_or_none()
            if pf:
                preflight_data = {
                    "overall_status": pf.overall_status,
                    "base_checks": pf.base_checks,
                    "mission_checks": pf.mission_checks,
                    "critical_failures": pf.critical_failures,
                    "summary": pf.summary,
                    "completed_at": pf.completed_at.isoformat() if pf.completed_at else None,
                }

        # Flight events summary (may be None if no flight linked)
        events_summary: dict = {"total": 0, "by_type": {}}
        if runtime.flight_id:
            total_q = await db.execute(
                select(func.count())
                .select_from(FlightEvent)
                .where(FlightEvent.flight_id == runtime.flight_id)
            )
            total = int(total_q.scalar() or 0)

            type_rows = (
                await db.execute(
                    select(FlightEvent.type, func.count())
                    .where(FlightEvent.flight_id == runtime.flight_id)
                    .group_by(FlightEvent.type)
                )
            ).all()
            by_type = {t: int(c) for t, c in type_rows}
            events_summary = {"total": total, "by_type": by_type}

        return {
            "mission": {
                "flight_id": runtime.client_flight_id,
                "mission_type": runtime.mission_type,
                "mission_name": runtime.mission_name,
                "state": runtime.state,
                "started_at": runtime.started_at.isoformat() if runtime.started_at else None,
                "ended_at": runtime.ended_at.isoformat() if runtime.ended_at else None,
                "operator_note": runtime.operator_note,
            },
            "compliance": {
                "id": comp.id,
                "remote_id_status": comp.remote_id_status,
                "laanc_auth_number": comp.laanc_auth_number,
                "laanc_auth_expires": (
                    comp.laanc_auth_expires.isoformat() if comp.laanc_auth_expires else None
                ),
                "preflight_ack_at": (
                    comp.preflight_ack_at.isoformat() if comp.preflight_ack_at else None
                ),
                "notes": comp.notes,
                "created_at": comp.created_at.isoformat(),
                "updated_at": comp.updated_at.isoformat(),
            } if comp else None,
            "preflight": preflight_data,
            "events_summary": events_summary,
        }
