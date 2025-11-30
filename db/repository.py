from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .session import Session
from .models import TelemetryRecord, Flight, FlightEvent, MavlinkEvent, VideoRecording, VideoFrame
from drone.models import Telemetry as TelemetryDTO
import logging
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
from typing import Iterable, Mapping, Optional, Dict, Any


class TelemetryRepository:
    def __init__(self, session_factory: type[Session] = Session):
        self._session_factory = session_factory

    # Backwards-compatible: save a loose telemetry row (no flight)
    async def save(self, t: TelemetryDTO) -> None:
        async with self._session_factory() as s:  # type: AsyncSession
            rec = TelemetryRecord(
                lat=t.lat, lon=t.lon, alt=t.alt,
                heading=t.heading, groundspeed=t.groundspeed,
                # armed=t.armed,
                mode=t.mode,
                battery_voltage=t.battery_voltage,
                battery_current=t.battery_current,
                battery_remaining=t.battery_remaining,
                system_time=getattr(t, "system_time", None),
            )
            s.add(rec)
            await s.commit()

    # ---- New flight-aware methods ----

    async def create_flight(
            self,
            *,
            started_at: Optional[datetime] = None,
            start_lat: float, start_lon: float, start_alt: float,
            dest_lat: float,  dest_lon: float,  dest_alt: float,
            status: str = "in_progress",
            note: str = "",
    ) -> int:
        started_at = started_at or datetime.now(timezone.utc)
        async with self._session_factory() as s:
            async with s.begin():
                f = Flight(
                    started_at=started_at,
                    status=status,
                    note=note,
                    start_lat=start_lat, start_lon=start_lon, start_alt=start_alt,
                    dest_lat=dest_lat, dest_lon=dest_lon, dest_alt=dest_alt,
                )
                s.add(f)
                await s.flush()       # populates f.id
                fid = f.id
                return fid

    async def add_event(self, flight_id: int, etype: str, data: Dict[str, Any] | None = None) -> None:
        async with self._session_factory() as s:
            async with s.begin():
                e = FlightEvent(flight_id=flight_id, type=etype, data=data or {})
                s.add(e)

    async def add_telemetry(self, flight_id: int, **fields) -> None:
        async with self._session_factory() as s:
            async with s.begin():
                fields.setdefault("flight_id", flight_id)
                fields.setdefault("system_time", None)
                rec = TelemetryRecord(flight_id=flight_id, **fields)
                s.add(rec)

    # ------- Faster bulk ingest APIs -------
    async def add_telemetry_many(self, flight_id: int, rows: Iterable[Mapping[str, Any]]) -> int:
        """Bulk insert telemetry. Each row is a dict of TelemetryRecord fields *excluding* id.
        Commits once. Returns number of rows inserted.
        Example row keys: row keys: lat, lon, alt, heading, groundspeed, armed, mode,
        battery_voltage, battery_current, battery_remaining
        """

        payload = []
        for r in rows:
            d = dict(r)
            d.setdefault("flight_id", flight_id)
            d.setdefault("system_time", None)
            payload.append(d)

        if not payload:
            return 0

        async with self._session_factory() as s:
            stmt = insert(TelemetryRecord).values(payload)
            await s.execute(stmt)
            await s.commit()
            return len(payload)

    async def finish_flight(self, flight_id: int, *, status: str, note: str = "") -> None:
        async with self._session_factory() as s:
            res = await s.execute(select(Flight).where(Flight.id == flight_id))
            f = res.scalar_one_or_none()
            if not f:
                logging.warning(f"finish_flight: flight {flight_id} not found")
                return
            f.status = status
            f.note = note
            f.ended_at = datetime.now(timezone.utc)
            await s.commit()


    async def add_mavlink_events_many(self, flight_id: int, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = []
        for r in rows:
            d = dict(r)
            d.setdefault("flight_id", flight_id)

            msg_type = d.get("msg_type") or d.get("payload", {}).get("mavpackettype") or "UNKNOWN"

            # Convert time_boot_ms (ms since boot) into some datetime.
            time_boot_ms = d.get("time_boot_ms")
            if isinstance(time_boot_ms, (int, float)):
                # Example heuristic: system time minus delta
                now = datetime.now(timezone.utc)
                time_boot_ms = now - timedelta(milliseconds=(0 if time_boot_ms < 0 else time_boot_ms))
            elif isinstance(time_boot_ms, datetime):
                pass
            else:
                time_boot_ms = datetime.now(timezone.utc)

            # Normalize timestamp to datetime
            ts = d.get("timestamp")
            if ts is not None and not isinstance(ts, datetime):
                try:
                    ts = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                except Exception:
                    ts = datetime.now(timezone.utc)
            elif ts is None:
                ts = datetime.now(timezone.utc)

            payload.append({
                "flight_id":      d["flight_id"],
                "msg_type":       msg_type,
                "time_boot_ms":   time_boot_ms,
                "time_unix_usec": d.get("time_unix_usec"),
                "timestamp":      ts,
                "payload":        d.get("payload", {}),
            })

        if not payload:
            return 0

        async with self._session_factory() as s:
            stmt = pg_insert(MavlinkEvent).values(payload)
            # optional: if you have a unique constraint on (flight_id, msg_type, time_boot_ms)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["flight_id", "msg_type", "time_boot_ms"]
            )

            try:
                await s.execute(stmt)
                await s.commit()
                logging.info(f"Successfully inserted {len(payload)} MavlinkEvent records for flight {flight_id}")
                return len(payload)
            except Exception as e:
                logging.error(f"Bulk insert failed for flight {flight_id}: {e}")
                await s.rollback()

                inserted = 0
                for d in payload:
                    try:
                        await s.execute(insert(MavlinkEvent).values(d))
                        await s.commit()
                        inserted += 1
                    except Exception as single_e:
                        logging.error(f"Single insert failed for flight {flight_id}: {single_e}")
                        await s.rollback()
                logging.info(f"Fallback single inserts completed: {inserted}/{len(payload)} records inserted")
                return inserted



    async def start_recording(
            self,
            *,
            flight_id: Optional[int],
            file_path: str,
            codec: str | None = None,
            width: int | None = None,
            height: int | None = None,
            fps: float | None = None,
            note: str = "",
    ) -> int:
        """Create a VideoRecording row and return its id."""
        async with self._session_factory() as s:
            rec = VideoRecording(
                flight_id=flight_id,
                file_path=file_path,
                codec=codec,
                width=width,
                height=height,
                fps=fps,
                note=note,
            )
            s.add(rec)
            await s.flush()
            rid = rec.id
            await s.commit()
            return rid

    async def finish_recording(
            self,
            recording_id: int,
            *,
            frame_count: int | None = None,
            size_bytes: int | None = None,
            ended_at: Optional[datetime] = None,
    ) -> None:
        async with self._session_factory() as s:
            q = await s.execute(
                select(VideoRecording).where(VideoRecording.id == recording_id)
            )
            rec = q.scalar_one()
            rec.ended_at = ended_at or datetime.now(timezone.utc)
            if frame_count is not None:
                rec.frame_count = frame_count
            if size_bytes is not None:
                rec.size_bytes = size_bytes
            await s.commit()

    async def add_video_frames_many(
            self,
            recording_id: int,
            rows: Iterable[Mapping[str, Any]],
    ) -> int:
        """Bulk-insert per-frame metadata (anomalies, thumbs, etc.)."""
        payload = []
        for r in rows:
            d = dict(r)
            d.setdefault("recording_id", recording_id)
            if "ts" not in d:
                d["ts"] = datetime.now(timezone.utc)
            payload.append(d)

        if not payload:
            return 0

        async with self._session_factory() as s:
            stmt = insert(VideoFrame).values(payload)
            await s.execute(stmt)
            await s.commit()
            return len(payload)

class TelemetryBuffer:
    def __init__(self, repo: TelemetryRepository, flight_id: int,
                 batch_size: int = 50, max_interval_sec: float = 1.0):
        self.repo = repo
        self.flight_id = flight_id
        self.batch_size = batch_size
        self.max_interval_sec = max_interval_sec

        self._buffer: list[dict] = []
        self._last_flush = datetime.now(timezone.utc)

    async def add(self, row: Mapping[str, Any]):
        self._buffer.append(dict(row))

        now = datetime.now(timezone.utc)
        too_many = len(self._buffer) >= self.batch_size
        too_old = (now - self._last_flush).total_seconds() >= self.max_interval_sec

        if too_many or too_old:
            await self.flush()

    async def flush(self):
        if not self._buffer:
            return
        await self.repo.add_telemetry_many(self.flight_id, self._buffer)
        self._buffer.clear()
        self._last_flush = datetime.now(timezone.utc)




