from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Iterable, Mapping, List, Tuple
from sqlalchemy import select, insert, func, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import TelemetryRecord, Flight, FlightEvent, MavlinkEvent, SettingsRow, VaultSecret
from backend.drone.models import Telemetry as TelemetryDTO
import logging
from .session import Session
from backend.utils.vault import Vault
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.models import Geofence
from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon, Point



logger = logging.getLogger(__name__)


class TelemetryRepository:
    def __init__(self, session_factory: type[Session] = Session):
        self._session_factory = session_factory

    # Backwards-compatible: save a loose telemetry row (no flight)
    async def save(self, t: TelemetryDTO) -> None:
        async with self._session_factory() as s:  # type: AsyncSession
            rec = TelemetryRecord(
                lat=t.lat,
                lon=t.lon,
                alt=t.alt,
                heading=t.heading,
                groundspeed=t.groundspeed,
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
        start_lat: float,
        start_lon: float,
        start_alt: float,
        dest_lat: float,
        dest_lon: float,
        dest_alt: float,
        status: str = "in_progress",
        note: str = "",
    ) -> int:
        started_at = started_at or datetime.now(timezone.utc)
        async with self._session_factory() as s:
            f = Flight(
                started_at=started_at,
                status=status,
                note=note,
                start_lat=start_lat,
                start_lon=start_lon,
                start_alt=start_alt,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                dest_alt=dest_alt,
            )
            s.add(f)
            await s.flush()  # populates f.id
            fid = f.id
            await s.commit()
            return fid

    async def add_event(
        self, flight_id: int, etype: str, data: Dict[str, Any] | None = None
    ) -> None:
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
    async def add_telemetry_many(
        self, flight_id: int, rows: Iterable[Mapping[str, Any]]
    ) -> int:
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

    async def finish_flight(
        self, flight_id: int, *, status: str, note: str = ""
    ) -> None:
        async with self._session_factory() as s:
            q = await s.execute(select(Flight).where(Flight.id == flight_id))
            f = q.scalar_one()
            f.status = status
            f.note = note
            f.ended_at = datetime.now(timezone.utc)
            await s.commit()

    # repository.py
    async def add_mavlink_events_many(
        self, flight_id: int, rows: Iterable[Mapping[str, Any]]
    ) -> int:
        """
        rows dict keys expected:
          - msg_type (str)               -> defaults to payload['mavpackettype'] or 'UNKNOWN'
          - time_boot_ms (int|None)      -> stored as ms since boot
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
            msg_type = (
                d.get("msg_type")
                or d.get("payload", {}).get("mavpackettype")
                or "UNKNOWN"
            )

            # Normalize time_boot_ms (ms since boot)
            time_boot_ms = d.get("time_boot_ms")
            if isinstance(time_boot_ms, (int, float)):
                try:
                    time_boot_ms = int(time_boot_ms)
                except Exception:
                    time_boot_ms = None
            else:
                time_boot_ms = None

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

            payload.append(
                {
                    "flight_id": d["flight_id"],
                    "msg_type": msg_type,
                    "time_boot_ms": time_boot_ms,
                    "time_unix_usec": d.get("time_unix_usec"),
                    "timestamp": ts,
                    "payload": d.get("payload", {}),
                }
            )

        if not payload:
            return 0

        async with self._session_factory() as s:
            stmt = insert(MavlinkEvent).values(payload)
            try:
                await s.execute(stmt)
                await s.commit()
                logger.info(
                    f"Successfully inserted {len(payload)} MavlinkEvent records for flight {flight_id}"
                )
                return len(payload)
            except Exception as e:
                logger.error(f"Bulk insert failed for flight {flight_id}: {e}")
                await s.rollback()
                inserted = 0
                for d in payload:
                    try:
                        await s.execute(insert(MavlinkEvent).values(d))
                        await s.commit()
                        inserted += 1
                    except Exception as single_e:
                        logger.error(
                            f"Single insert failed for flight {flight_id}: {single_e}"
                        )
                        await s.rollback()
                logger.info(
                    f"Fallback single inserts completed: {inserted}/{len(payload)} records inserted"
                )
                return inserted



MASK = "********"


class SettingsRepository:


    def __init__(self) -> None:
        self._session_factory = Session
        self._vault = Vault()

    async def get_settings_doc(self) -> Dict[str, Any]:
        async with self._session_factory() as db:
            res = await db.execute(select(SettingsRow).where(SettingsRow.id == 1))
            row = res.scalar_one_or_none()
            data = row.data if row else {}

            # attach masked secret fields
            secrets = await db.execute(select(VaultSecret))
            sec_rows = secrets.scalars().all()
            sec_names = {s.name for s in sec_rows}

            # only expose the ones your UI expects
            general = data.get("general", {})
            if "llm_api_key" in sec_names:
                general["llm_api_key"] = MASK
            if "mqtt_pass" in sec_names:
                general["mqtt_pass"] = MASK
            data["general"] = general

            # updated_at is handy for UI
            if row and getattr(row, "updated_at", None):
                data["updated_at"] = row.updated_at.isoformat()

            return data

    async def put_settings_doc(self, incoming: Dict[str, Any]) -> Dict[str, Any]:
        """
        - Upsert non-secret data into SettingsRow(id=1)
        - If incoming contains a non-masked secret, encrypt+store in VaultSecret
        - Return saved doc with masked secrets
        """
        async with self._session_factory() as db:
            data = dict(incoming)

            # --- secrets handling ---
            general = dict(data.get("general", {}) or {})

            # helper: update secret only if provided and not masked/empty
            async def upsert_secret(name: str, value: Optional[str]) -> None:
                if value is None:
                    return
                v = str(value).strip()
                if not v or v == MASK:
                    return
                ct = self._vault.encrypt(v)
                stmt = (
                    pg_insert(VaultSecret)
                    .values(name=name, ciphertext=ct)
                    .on_conflict_do_update(
                        index_elements=[VaultSecret.name],
                        set_={"ciphertext": ct},
                    )
                )
                await db.execute(stmt)

            #variables save with Vault
            await upsert_secret("llm_api_key", general.get("llm_api_key"))
            await upsert_secret("mqtt_pass", general.get("mqtt_pass"))
            await upsert_secret("raspberry_ip", general.get("raspberry_ip"))
            await upsert_secret("raspberry_password", general.get("raspberry_password"))
            await upsert_secret("raspberry_password", general.get("raspberry_password"))

            # never store plaintext secrets in settings JSON
            general.pop("llm_api_key", None)
            general.pop("mqtt_pass", None)
            data["general"] = general

            # --- upsert settings JSON ---
            stmt = (
                pg_insert(SettingsRow)
                .values(id=1, data=data)
                .on_conflict_do_update(
                    index_elements=[SettingsRow.id],
                    set_={"data": data},
                )
            )
            await db.execute(stmt)
            await db.commit()

        # return fresh doc with masked secrets
        return await self.get_settings_doc()


class GeofenceRepository:

    def __init__(self) -> None:
        self._session_factory = Session


    async def save_geofence_geojson(
            db: AsyncSession,
            *,
            name: str,
            coordinates_lonlat: list[list[float]],
            min_alt_m: float | None = None,
            max_alt_m: float | None = None,
    ):

        # GeoJSON gives [lon, lat]
        polygon = Polygon(coordinates_lonlat)

        geofence = Geofence(
            name=name,
            polygon=from_shape(polygon, srid=4326),
            min_alt_m=min_alt_m,
            max_alt_m=max_alt_m,
        )

        db.add(geofence)
        await db.commit()
        await db.refresh(geofence)

        return geofence


    async def is_point_inside_geofence(
            db: AsyncSession,
            *,
            geofence_name: str,
            lat: float,
            lon: float,
    ) -> bool:

        point = from_shape(Point(lon, lat), srid=4326)

        stmt = (
            select(Geofence.id)
            .where(Geofence.name == geofence_name)
            .where(Geofence.is_active == True)
            .where(func.ST_Contains(Geofence.polygon, point))
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None


    async def validate_mission_waypoints(
            db: AsyncSession,
            geofence_name: str,
            waypoints: list[tuple[float, float]],
    ):

        for lat, lon in waypoints:
            inside = await is_point_inside_geofence(
                db,
                geofence_name=geofence_name,
                lat=lat,
                lon=lon,
            )
            if not inside:
                return False

        return True