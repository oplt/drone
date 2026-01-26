from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Iterable, Mapping, Callable
from sqlalchemy import select, insert as sa_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .session import get_db_session
from .models import TelemetryRecord, Flight, FlightEvent, MavlinkEvent
from drone.models import Telemetry as TelemetryDTO
import logging
from .models import User


# Add to repository.py
class UserRepository:
    def __init__(self, session_factory: Callable = get_db_session):
        self._session_factory = session_factory

    async def create_user(
        self, username: str, email: str, password: str, is_admin: bool = False
    ) -> User:
        """Create a new user"""
        async with self._session_factory() as session:
            user = User(username=username, email=email, is_admin=is_admin)
            user.set_password(password)
            session.add(user)
            await session.commit()
            await session.refresh(user)  # Refresh to get ID and other defaults
            return user

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()

    async def authenticate_user(
        self, username_or_email: str, password: str
    ) -> Optional[User]:
        """Authenticate user by username/email and password"""
        # Try username first
        user = await self.get_user_by_username(username_or_email)
        if not user:
            # Try email
            user = await self.get_user_by_email(username_or_email)

        if user and user.check_password(password) and user.is_active:
            # Update last login in the same session where user was loaded
            # Merge user into a new session to update
            async with self._session_factory() as session:
                # Merge the user into this session
                merged_user = await session.merge(user)
                merged_user.last_login = datetime.now(timezone.utc)
                await session.commit()
                # Refresh to get updated user
                await session.refresh(merged_user)
            return merged_user
        return None

    async def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user information"""
        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user:
                for key, value in kwargs.items():
                    if key == "password":
                        user.set_password(value)
                    elif hasattr(user, key):
                        setattr(user, key, value)

                await session.commit()
                return user
            return None

    async def delete_user(self, user_id: int) -> bool:
        """Soft delete user (deactivate)"""
        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user:
                user.is_active = False
                await session.commit()
                return True
            return False


class TelemetryRepository:
    def __init__(self, session_factory: Callable = get_db_session):
        self._session_factory = session_factory

    # Backwards-compatible: save a loose telemetry row (no flight)
    async def save(self, t: TelemetryDTO) -> None:
        async with self._session_factory() as s:
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
        user_id: Optional[int] = None,
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
                user_id=user_id,
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

    async def add_telemetry_many_optimized(
        self, flight_id: int, rows: Iterable[Mapping[str, Any]]
    ) -> int:
        """Optimized bulk insert with single session"""
        rows_list = list(rows)
        if not rows_list:
            return 0

        BATCH_SIZE = 2000  # Optimized batch size to balance memory and performance
        total_inserted = 0

        async with self._session_factory() as session:
            for i in range(0, len(rows_list), BATCH_SIZE):
                batch = rows_list[i : i + BATCH_SIZE]
                payload = [
                    {
                        **dict(r),
                        "flight_id": flight_id,
                        "created_at": datetime.now(timezone.utc),
                    }
                    for r in batch
                ]

                if payload:
                    await session.execute(sa_insert(TelemetryRecord).values(payload))
                    total_inserted += len(payload)

            await session.commit()  # SINGLE COMMIT

        return total_inserted

    async def _fallback_single_inserts(
        self, flight_id: int, batch: list, session
    ) -> int:
        """Fallback to single inserts if batch fails"""
        inserted = 0
        for row in batch:
            try:
                d = dict(row)
                d.setdefault("flight_id", flight_id)
                stmt = sa_insert(TelemetryRecord).values(d)
                await session.execute(stmt)
                inserted += 1
            except Exception as e:
                logging.debug(f"Single insert failed: {e}")
                continue
        return inserted

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

    async def add_mavlink_events_many(
        self, flight_id: int, rows: Iterable[Mapping[str, Any]]
    ) -> int:
        """OPTIMIZED version with batch processing"""
        # Convert to list and pre-process
        rows_list = []
        now = datetime.now(timezone.utc)

        for r in rows:
            d = dict(r)
            d.setdefault("flight_id", flight_id)
            d.setdefault(
                "msg_type", d.get("payload", {}).get("mavpackettype", "UNKNOWN")
            )

            # Optimize timestamp parsing
            ts = d.get("timestamp")
            if not isinstance(ts, datetime):
                try:
                    if ts is not None:
                        ts = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                    else:
                        ts = now
                except (ValueError, TypeError):
                    ts = now
            d["timestamp"] = ts

            rows_list.append(d)

        if not rows_list:
            return 0

        # Batch process for performance
        BATCH_SIZE = 500  # Mavlink events can be smaller
        total_inserted = 0

        for i in range(0, len(rows_list), BATCH_SIZE):
            batch = rows_list[i : i + BATCH_SIZE]
            payload = []

            for d in batch:
                payload.append(
                    {
                        "flight_id": d["flight_id"],
                        "msg_type": d["msg_type"],
                        "timestamp": d["timestamp"],
                        "payload": d.get("payload", {}),
                        "time_boot_ms": d.get("time_boot_ms"),
                        "time_unix_usec": d.get("time_unix_usec"),
                    }
                )

            try:
                async with self._session_factory() as session:
                    # Use ON CONFLICT DO NOTHING for duplicates
                    bind_url = None
                    try:
                        bind_url = str(session.bind.url)
                    except Exception:
                        bind_url = None

                    if bind_url and "postgresql" in bind_url:
                        stmt: Any = (
                            pg_insert(MavlinkEvent)
                            .values(payload)
                            .on_conflict_do_nothing(
                                index_elements=["flight_id", "msg_type", "time_boot_ms"]
                            )
                        )
                    else:
                        stmt = sa_insert(MavlinkEvent).values(payload)

                    await session.execute(stmt)
                    await session.commit()
                    total_inserted += len(payload)

            except Exception as e:
                logging.error(f"Mavlink batch insert failed: {e}")
                # Fallback to individual inserts with single session to avoid pool exhaustion
                inserted_in_batch = 0
                try:
                    async with self._session_factory() as session:
                        for item in payload:
                            try:
                                stmt = sa_insert(MavlinkEvent).values(item)
                                await session.execute(stmt)
                                inserted_in_batch += 1
                            except Exception as item_err:
                                logging.debug(f"Single item insert failed: {item_err}")
                                continue
                        # Single commit for all successful inserts
                        await session.commit()
                except Exception as fallback_err:
                    logging.error(f"Fallback insert session failed: {fallback_err}")
                    # If even fallback fails, log and continue
                total_inserted += inserted_in_batch

        return total_inserted
