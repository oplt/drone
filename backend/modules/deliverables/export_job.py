from __future__ import annotations

import csv
import io
import json
import logging
import os
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


async def run_mission_export(flight_id: str, user_id: int, org_id: int | None, job_id: int) -> None:
    from sqlalchemy import select, update

    from backend.core.config.runtime import settings
    from backend.core.database.session import Session
    from backend.modules.deliverables.models import ExportJob
    from backend.modules.integrations.webhooks.service import WebhookDispatchService
    from backend.modules.missions.command_models import OperatorCommand
    from backend.modules.missions.flight_models import Flight, FlightEvent
    from backend.modules.missions.runtime_models import MissionRuntime
    from backend.modules.preflight.models import PreflightRun
    from backend.modules.telemetry.models import TelemetryRecord

    async with Session() as db:
        export_job = await db.get(ExportJob, job_id)
        if export_job is None:
            raise ValueError(f"ExportJob {job_id} not found")
        if export_job.status == "ready" and export_job.download_url:
            return
        await db.execute(update(ExportJob).where(ExportJob.id == job_id).values(status="running"))
        await db.commit()

        try:
            q = await db.execute(
                select(MissionRuntime).where(MissionRuntime.client_flight_id == flight_id)
            )
            runtime = q.scalar_one_or_none()

            flight = None
            if runtime and runtime.flight_id:
                q2 = await db.execute(
                    select(
                        Flight.id,
                        Flight.started_at,
                        Flight.ended_at,
                    ).where(Flight.id == runtime.flight_id)
                )
                flight = q2.one_or_none()

            events = []
            if flight:
                q3 = await db.execute(
                    select(
                        FlightEvent.id,
                        FlightEvent.type,
                        FlightEvent.created_at,
                        FlightEvent.data,
                    ).where(FlightEvent.flight_id == flight.id)
                )
                events = list(q3.all())

            telemetry_stmt = None
            if flight:
                telemetry_stmt = (
                    select(
                        TelemetryRecord.created_at,
                        TelemetryRecord.lat,
                        TelemetryRecord.lon,
                        TelemetryRecord.alt,
                        TelemetryRecord.heading,
                        TelemetryRecord.groundspeed,
                        TelemetryRecord.battery_remaining,
                        TelemetryRecord.mode,
                    )
                    .where(TelemetryRecord.flight_id == flight.id)
                    .order_by(TelemetryRecord.created_at)
                    .execution_options(yield_per=1000)
                )

            preflight = None
            if runtime and runtime.preflight_run_id:
                q5 = await db.execute(
                    select(PreflightRun).where(PreflightRun.id == runtime.preflight_run_id)
                )
                preflight = q5.scalar_one_or_none()

            commands = []
            if runtime:
                q6 = await db.execute(
                    select(
                        OperatorCommand.command_id,
                        OperatorCommand.command,
                        OperatorCommand.state_before,
                        OperatorCommand.state_after,
                        OperatorCommand.accepted,
                        OperatorCommand.message,
                        OperatorCommand.reason,
                        OperatorCommand.requested_at,
                    )
                    .where(OperatorCommand.client_flight_id == flight_id)
                    .order_by(OperatorCommand.requested_at)
                )
                commands = list(q6.all())

            telemetry_stream = (
                await db.stream(telemetry_stmt) if telemetry_stmt is not None else None
            )

            # The archive itself is buffered for object-storage upload, but
            # telemetry is written row-by-row into the ZIP entry.
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                manifest = {
                    "flight_id": flight_id,
                    "org_id": org_id,
                    "exported_by_user_id": user_id,
                    "exported_at": datetime.now(UTC).isoformat(),
                    "mission_name": runtime.mission_name if runtime else None,
                    "mission_type": runtime.mission_type if runtime else None,
                    "state": runtime.state if runtime else None,
                    "started_at": runtime.started_at.isoformat()
                    if runtime and runtime.started_at
                    else None,
                    "ended_at": runtime.ended_at.isoformat()
                    if runtime and runtime.ended_at
                    else None,
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))

                with zf.open("telemetry.csv", "w") as telemetry_file, io.TextIOWrapper(
                    telemetry_file, encoding="utf-8", newline=""
                ) as telemetry_text:
                        writer = csv.writer(telemetry_text)
                        writer.writerow(
                            [
                                "timestamp",
                                "lat",
                                "lon",
                                "alt",
                                "heading",
                                "groundspeed",
                                "battery_remaining",
                                "mode",
                            ]
                        )
                        if telemetry_stream is not None:
                            async for t in telemetry_stream:
                                writer.writerow(
                                    [
                                        t.created_at.isoformat(),
                                        t.lat,
                                        t.lon,
                                        t.alt,
                                        t.heading,
                                        t.groundspeed,
                                        t.battery_remaining,
                                        t.mode,
                                    ]
                                )

                events_data = [
                    {
                        "id": e.id,
                        "type": e.type,
                        "created_at": e.created_at.isoformat(),
                        "data": e.data,
                    }
                    for e in events
                ]
                zf.writestr("events.json", json.dumps(events_data, indent=2))

                if preflight:
                    pf_data = {
                        "run_uuid": preflight.run_uuid,
                        "overall_status": preflight.overall_status,
                        "base_checks": preflight.base_checks,
                        "mission_checks": preflight.mission_checks,
                        "critical_failures": preflight.critical_failures,
                        "summary": preflight.summary,
                        "started_at": preflight.started_at.isoformat(),
                        "completed_at": preflight.completed_at.isoformat()
                        if preflight.completed_at
                        else None,
                    }
                    zf.writestr("preflight.json", json.dumps(pf_data, indent=2))

                cmds_data = [
                    {
                        "command_id": c.command_id,
                        "command": c.command,
                        "state_before": c.state_before,
                        "state_after": c.state_after,
                        "accepted": c.accepted,
                        "message": c.message,
                        "reason": c.reason,
                        "requested_at": c.requested_at.isoformat(),
                    }
                    for c in commands
                ]
                zf.writestr("commands.json", json.dumps(cmds_data, indent=2))

            buf.seek(0)
            zip_bytes = buf.read()

            download_url: str | None = None
            expires_at: datetime | None = None

            if settings.storage_backend == "s3":
                from backend.infrastructure.storage import ObjectStorageClient

                org_prefix = f"orgs/{org_id}" if org_id else "orgs/shared"
                object_key = f"{org_prefix}/exports/{flight_id}.zip"
                client = ObjectStorageClient()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                    tmp.write(zip_bytes)
                    tmp_path = tmp.name
                try:
                    from pathlib import Path

                    await client.upload_file(Path(tmp_path), object_key)
                    download_url = await client.generate_presigned_url(object_key, expires_in=86400)
                    expires_at = datetime.now(UTC) + timedelta(seconds=86400)
                finally:
                    os.unlink(tmp_path)
            else:
                export_dir = os.path.join("backend", "storage", "exports")
                os.makedirs(export_dir, exist_ok=True)
                local_path = os.path.join(export_dir, f"{flight_id}.zip")
                with open(local_path, "wb") as f:
                    f.write(zip_bytes)
                download_url = f"/exports/{flight_id}.zip"

            await db.execute(
                update(ExportJob)
                .where(ExportJob.id == job_id)
                .values(
                    status="ready",
                    download_url=download_url,
                    expires_at=expires_at,
                    completed_at=datetime.now(UTC),
                )
            )
            await WebhookDispatchService().enqueue(
                db,
                org_id=org_id,
                event_type="export.ready",
                payload={"id": job_id, "flight_id": flight_id, "download_url": download_url},
                idempotency_key=f"export.ready:{job_id}",
            )
            await db.commit()

        except Exception as exc:
            logger.exception("Export task failed for flight %s: %s", flight_id, exc)
            await db.execute(
                update(ExportJob)
                .where(ExportJob.id == job_id)
                .values(
                    status="failed",
                    error=str(exc)[:512],
                    completed_at=datetime.now(UTC),
                )
            )
            await db.commit()
            raise
