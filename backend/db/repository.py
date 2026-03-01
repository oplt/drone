from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Iterable, Mapping, List, Tuple
from sqlalchemy import select, insert, func, literal_column, delete
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


# Vault keys (names stored in VaultSecret.name)
V_TELEM_MQTT_PASS = "telemetry.mqtt_pass"
V_AI_LLM_KEY = "ai.llm_api_key"
V_PI_PASS = "raspberry.raspberry_password"

SECRET_PATHS = {
    V_TELEM_MQTT_PASS: ("telemetry", "mqtt_pass"),
    V_AI_LLM_KEY: ("ai", "llm_api_key"),
    V_PI_PASS: ("raspberry", "raspberry_password"),
}


def _ensure_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override into base (dict-dict recursively)."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _set_path(d: Dict[str, Any], path: tuple[str, str], value: Any) -> None:
    a, b = path
    d.setdefault(a, {})
    if isinstance(d[a], dict):
        d[a][b] = value


def _pop_path(d: Dict[str, Any], path: tuple[str, str]) -> Optional[Any]:
    a, b = path
    if not isinstance(d.get(a), dict):
        return None
    return d[a].pop(b, None)


class SettingsRepository:
    def __init__(self) -> None:
        self._session_factory = Session
        self._vault = Vault()

    async def _read_row(self) -> tuple[Dict[str, Any], Optional[str]]:
        async with self._session_factory() as db:
            res = await db.execute(select(SettingsRow).where(SettingsRow.id == 1))
            row = res.scalar_one_or_none()
            data = (row.data if row else {}) or {}
            updated_at = row.updated_at.isoformat() if row and getattr(row, "updated_at", None) else None
            return dict(data), updated_at

    async def _read_secret_names(self) -> set[str]:
        async with self._session_factory() as db:
            sec = await db.execute(select(VaultSecret.name))
            return {r[0] for r in sec.all()}

    async def get_settings_doc(self) -> Dict[str, Any]:
        """
        Public (UI) shape:
        - returns SettingsDoc-compatible dict
        - secrets are masked if present in vault
        """
        data, updated_at = await self._read_row()

        # Ensure top-level sections exist so UI doesn't crash on undefined access
        data = _deep_merge(
            {
                "telemetry": {},
                "ai": {},
                "credentials": {},
                "hardware": {},
                "preflight": {},
                "raspberry": {},
                "camera": {},
            },
            data,
        )

        sec_names = await self._read_secret_names()
        for secret_name, path in SECRET_PATHS.items():
            if secret_name in sec_names:
                _set_path(data, path, MASK)

        if updated_at:
            data["updated_at"] = updated_at

        return data

    async def put_settings_doc(self, incoming: Dict[str, Any]) -> Dict[str, Any]:
        """
        - Upsert non-secret settings JSON into SettingsRow(id=1)
        - If incoming contains a non-masked secret, encrypt+store it in VaultSecret
        - Never stores plaintext secrets in SettingsRow.data
        - Returns saved doc with masked secrets
        """
        # Normalize and ensure sections exist
        data = _ensure_dict(incoming)

        # updated_at should be DB-derived, not stored
        data.pop("updated_at", None)

        data = _deep_merge(
            {
                "telemetry": {},
                "ai": {},
                "credentials": {},
                "hardware": {},
                "preflight": {},
                "raspberry": {},
                "camera": {},
            },
            data,
        )

        async with self._session_factory() as db:

            async def upsert_secret(name: str, value: Optional[str]) -> None:
                if value is None:
                    return
                raw = str(value)
                if raw == MASK:
                    return
                if not raw.strip():
                    await db.execute(delete(VaultSecret).where(VaultSecret.name == name))
                    return
                ct = self._vault.encrypt(raw)
                stmt = (
                    pg_insert(VaultSecret)
                    .values(name=name, ciphertext=ct)
                    .on_conflict_do_update(
                        index_elements=[VaultSecret.name],
                        set_={"ciphertext": ct},
                    )
                )
                await db.execute(stmt)

            # --- extract + store secrets (then remove from JSON) ---
            mqtt_pass = _pop_path(data, SECRET_PATHS[V_TELEM_MQTT_PASS])
            llm_key = _pop_path(data, SECRET_PATHS[V_AI_LLM_KEY])
            pi_pass = _pop_path(data, SECRET_PATHS[V_PI_PASS])

            await upsert_secret(V_TELEM_MQTT_PASS, mqtt_pass)
            await upsert_secret(V_AI_LLM_KEY, llm_key)
            await upsert_secret(V_PI_PASS, pi_pass)

            # --- upsert non-secret JSON ---
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

        return await self.get_settings_doc()

    async def get_effective_settings_doc(self) -> Dict[str, Any]:
        """
        Internal runtime shape:
        - returns SettingsDoc-compatible dict
        - secrets are decrypted and injected into the SAME nested paths the UI uses
        """
        data, updated_at = await self._read_row()

        data = _deep_merge(
            {
                "telemetry": {},
                "ai": {},
                "credentials": {},
                "hardware": {},
                "preflight": {},
                "raspberry": {},
                "camera": {},
            },
            data,
        )

        async with self._session_factory() as db:
            sec_res = await db.execute(select(VaultSecret))
            secrets = {s.name: s.ciphertext for s in sec_res.scalars().all()}

        def dec(name: str) -> str:
            ct = secrets.get(name)
            if not ct:
                return ""
            raw = self._vault.decrypt(ct)
            # Vault.decrypt may already return bytes or str depending on your impl
            return raw.decode("utf-8") if hasattr(raw, "decode") else str(raw)

        for secret_name, path in SECRET_PATHS.items():
            _set_path(data, path, dec(secret_name))

        if updated_at:
            data["updated_at"] = updated_at

        return data

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
