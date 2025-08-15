from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Iterable, Mapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from .session import Session
from .models import TelemetryRecord, Flight, FlightEvent, MavlinkEvent
from drone.models import Telemetry as TelemetryDTO
import logging

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
            await s.commit()
            return fid

    async def add_event(self, flight_id: int, etype: str, data: Dict[str, Any] | None = None) -> None:
        async with self._session_factory() as s:
            e = FlightEvent(flight_id=flight_id, type=etype, data=data or {})
            s.add(e)
            await s.commit()

    async def add_telemetry(self, flight_id: int, **fields) -> None:
        async with self._session_factory() as s:
            rec = TelemetryRecord(flight_id=flight_id, **fields)
            s.add(rec)
            await s.commit()

    # ------- Faster bulk ingest APIs -------
    async def add_telemetry_many(self, flight_id: int, rows: Iterable[Mapping[str, Any]]) -> int:
        """Bulk insert telemetry. Each row is a dict of TelemetryRecord fields *excluding* id.
        Commits once. Returns number of rows inserted.
        Example row keys: lat, lon, alt, heading, groundspeed, armed, mode, battery_voltage, battery_current, battery_level
        created_at and flight_id will be set automatically if omitted.
        """
        payload = []
        for r in rows:
            d = dict(r)
            d.setdefault("flight_id", flight_id)
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
            q = await s.execute(select(Flight).where(Flight.id == flight_id))
            f = q.scalar_one()
            f.status = status
            f.note = note
            f.ended_at = datetime.now(timezone.utc)
            await s.commit()


    # repository.py
    async def add_mavlink_events_many(self, flight_id: int, rows: Iterable[Mapping[str, Any]]) -> int:
        """
        rows dict keys expected:
          - msg_type (str)               -> defaults to payload['mavpackettype'] or 'UNKNOWN'
          - time_boot_ms (int|None)      -> converted to datetime if provided
          - time_unix_usec (datetime|None)  # already converted in mqtt.py
          - timestamp (datetime|None)       # we'll also accept raw numeric and convert here
          - payload (dict)
          - flight_id is set here if missing
        """
        payload = []
        for r in rows:
            d = dict(r)
            d.setdefault("flight_id", flight_id)
            # derive msg_type if missing
            msg_type = d.get("msg_type") or d.get("payload", {}).get("mavpackettype") or "UNKNOWN"

            # Convert time_boot_ms from milliseconds to datetime if provided
            time_boot_ms = d.get("time_boot_ms")
            if time_boot_ms is not None and isinstance(time_boot_ms, (int, float)):
                try:
                    # Convert milliseconds to datetime (assuming boot time is relative to epoch)
                    # This is a rough approximation - in practice you might want to use system time
                    time_boot_ms = datetime.fromtimestamp(time_boot_ms / 1000.0, tz=timezone.utc)
                except Exception:
                    time_boot_ms = datetime.now(timezone.utc)
            elif time_boot_ms is None:
                # Set default timestamp if not provided
                time_boot_ms = datetime.now(timezone.utc)

            # normalize timestamp if someone passed numeric seconds
            ts = d.get("timestamp")
            if ts is not None and not isinstance(ts, datetime):
                try:
                    # handle int/float epoch seconds
                    ts = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                except Exception:
                    ts = datetime.now(timezone.utc)
            elif ts is None:
                ts = datetime.now(timezone.utc)

            payload.append({
                "flight_id":     d["flight_id"],
                "msg_type":      msg_type,
                "time_boot_ms":  time_boot_ms,
                "time_unix_usec": d.get("time_unix_usec"),
                "timestamp":     ts,
                "payload":       d.get("payload", {}),
            })

        if not payload:
            return 0

        async with self._session_factory() as s:
            stmt = insert(MavlinkEvent).values(payload)
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


