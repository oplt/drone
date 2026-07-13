from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.core.events import (
    AlertEventEnvelopeV1,
    AlertEventPayloadV1,
    AlertSnapshotV1,
    TelemetryPayloadV1,
    mission_context_from_runtime,
    next_runtime_sequence,
    utc_now,
)
from backend.infrastructure.cache.locks import distributed_lock
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.alerts.recipient_parsing import parse_delimited_tokens
from backend.modules.alerts.repository import AlertRepository
from backend.modules.automation.outbox_repository import OutboxRepository
from backend.modules.geofences.models import Geofence
from backend.modules.livestock.models import Herd
from backend.modules.livestock.risk_service import RiskEngine
from backend.modules.patrol.service.mission_runtime_store import mission_runtime_store

logger = logging.getLogger(__name__)

MANAGED_RULE_TYPES = (
    "geofence_breach",
    "low_battery",
    "weak_link",
    "high_wind",
    "herd_isolation",
)


@dataclass(slots=True)
class AlertSignal:
    rule_type: str
    dedupe_key: str
    source: str
    severity: str
    title: str
    message: str
    meta_data: dict[str, Any]


class AlertEngine:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._repo = AlertRepository()
        self._outbox = OutboxRepository()
        self._risk = RiskEngine()
        self._last_db_error_log_at = 0.0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="OperationalAlertEngine")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None

    async def _loop(self) -> None:
        logger.info("Operational alert engine loop started")
        while self._running:
            started = time.monotonic()
            try:
                await self.evaluate_once()
            except SQLAlchemyError as exc:
                now = time.monotonic()
                if now - self._last_db_error_log_at >= 60.0:
                    logger.warning(
                        "Operational alert evaluation skipped: database unavailable: %s",
                        exc,
                    )
                    self._last_db_error_log_at = now
            except Exception:
                logger.exception("Operational alert evaluation failed")

            interval = max(2, int(settings.alerts_check_interval_sec or 5))
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.2, interval - elapsed))
        logger.info("Operational alert engine loop stopped")

    async def evaluate_once(self) -> None:
        """Run one leased evaluation cycle.

        API replicas may all start the alert engine. A short Redis lease keeps
        one replica from duplicating alert writes and notification work.
        """
        try:
            async with distributed_lock(
                "lock:alerts:evaluation",
                timeout=max(30, int(settings.alerts_check_interval_sec or 5) * 2),
                blocking_timeout=0.1,
            ):
                await self._evaluate_once()
        except TimeoutError:
            logger.debug("Skipping alert evaluation; another replica owns the lease")

    async def _evaluate_once(self) -> None:
        if not settings.alerts_enabled:
            return

        now = self._repo.utcnow()
        dedupe_window_sec = max(30, int(settings.alerts_dedupe_window_sec or 300))

        async with Session() as db:
            signals = await self._evaluate_signals(db)
            active_alerts = await self._repo.get_active_alerts_for_rules(
                db,
                rule_types=MANAGED_RULE_TYPES,
            )
            active_by_key = {a.dedupe_key: a for a in active_alerts}
            signal_by_key = {signal.dedupe_key: signal for signal in signals}

            events: list[tuple[str, AlertSnapshotV1, int]] = []
            notify_queue: list[tuple[AlertSnapshotV1, int, int | None]] = []

            for signal in signals:
                current = active_by_key.get(signal.dedupe_key)
                if current is None:
                    created = await self._repo.create_alert(
                        db,
                        rule_type=signal.rule_type,
                        dedupe_key=signal.dedupe_key,
                        source=signal.source,
                        severity=signal.severity,
                        title=signal.title,
                        message=signal.message,
                        meta_data=signal.meta_data,
                        now=now,
                    )
                    snapshot = AlertSnapshotV1.from_alert(created)
                    events.append(("created", snapshot, created.id))
                    notify_queue.append((snapshot, created.id, created.org_id))
                    continue

                should_notify = False
                if current.last_notified_at is None:
                    should_notify = True
                else:
                    age = (now - current.last_notified_at).total_seconds()
                    should_notify = age >= dedupe_window_sec

                should_update = (
                    should_notify
                    or current.severity != signal.severity
                    or current.title != signal.title
                    or current.message != signal.message
                    or current.meta_data != signal.meta_data
                )
                if should_update:
                    updated = await self._repo.touch_alert(
                        db,
                        alert=current,
                        severity=signal.severity,
                        title=signal.title,
                        message=signal.message,
                        meta_data=signal.meta_data,
                        now=now,
                        mark_notified=should_notify,
                    )
                    if should_notify:
                        snapshot = AlertSnapshotV1.from_alert(updated)
                        events.append(("updated", snapshot, updated.id))
                        notify_queue.append((snapshot, updated.id, updated.org_id))

            for dedupe_key, active in active_by_key.items():
                if dedupe_key in signal_by_key:
                    continue
                resolved = await self._repo.resolve_alert(db, alert=active, now=now)
                snapshot = AlertSnapshotV1.from_alert(resolved)
                events.append(("resolved", snapshot, resolved.id))

            outbox_events: list[dict[str, Any]] = []
            for payload, alert_id, org_id in notify_queue:
                notified = payload.last_notified_at or now
                outbox_events.append(
                    {
                        "event_type": "alert.notify",
                        "aggregate_type": "operational_alert",
                        "aggregate_id": str(alert_id),
                        "idempotency_key": f"alert.notify:{alert_id}:{notified.isoformat()}",
                        "payload": {"alert_id": alert_id, "alert": payload.to_legacy_alert_dict()},
                    }
                )
                if org_id is not None:
                    outbox_events.append(
                        {
                            "event_type": "webhook.dispatch",
                            "aggregate_type": "alert.triggered",
                            "aggregate_id": str(alert_id),
                            "idempotency_key": (
                                f"webhook:alert.triggered:{alert_id}:{notified.isoformat()}"
                            ),
                            "payload": {
                                "event": "alert.triggered",
                                "org_id": org_id,
                                "data": payload.to_legacy_alert_dict(),
                                "timestamp": notified.isoformat(),
                            },
                        }
                    )

            await self._outbox.enqueue_many(db, events=outbox_events)

            await db.commit()

        for action, payload, alert_id in events:
            await self._emit_in_app_event(action=action, payload=payload, alert_id=alert_id)

    async def _evaluate_signals(self, db: AsyncSession) -> list[AlertSignal]:
        telemetry_envelope = telemetry_manager.get_last_telemetry_envelope()
        signals: list[AlertSignal] = []
        signals.extend(
            await self._evaluate_drone_signals(
                db,
                telemetry_envelope.payload if telemetry_envelope else None,
                telemetry_envelope.emitted_at.timestamp() if telemetry_envelope else None,
            )
        )
        signals.extend(await self._evaluate_herd_signals(db))
        return signals

    async def _evaluate_drone_signals(
        self,
        db: AsyncSession,
        telemetry: TelemetryPayloadV1 | None,
        telemetry_timestamp_s: float | None,
    ) -> list[AlertSignal]:
        signals: list[AlertSignal] = []
        telemetry_ts = self._to_float(telemetry_timestamp_s)
        if telemetry is None or telemetry_ts is None or telemetry_ts <= 0:
            return signals

        battery_remaining = self._to_float(telemetry.battery.remaining_pct)
        low_battery_threshold = float(settings.alerts_low_battery_percent or 25.0)
        if (
            battery_remaining is not None
            and battery_remaining >= 0
            and battery_remaining <= low_battery_threshold
        ):
            signals.append(
                AlertSignal(
                    rule_type="low_battery",
                    dedupe_key="drone.low_battery",
                    source="drone",
                    severity="high",
                    title="Low Battery",
                    message=(
                        f"Battery dropped to {battery_remaining:.0f}% "
                        f"(threshold {low_battery_threshold:.0f}%)."
                    ),
                    meta_data={
                        "battery_remaining": battery_remaining,
                        "threshold_percent": low_battery_threshold,
                    },
                )
            )

        link_values = [
            self._to_float(telemetry.link.rc_quality_pct),
            self._to_float(telemetry.link.telemetry_quality_pct),
        ]
        valid_link_values = [v for v in link_values if v is not None and v >= 0]
        weak_link_threshold = float(settings.alerts_weak_link_percent or 35.0)
        if valid_link_values:
            weakest_link = min(valid_link_values)
            if weakest_link <= weak_link_threshold:
                signals.append(
                    AlertSignal(
                        rule_type="weak_link",
                        dedupe_key="drone.weak_link",
                        source="drone",
                        severity="medium",
                        title="Weak Telemetry Link",
                        message=(
                            f"Telemetry link quality degraded to {weakest_link:.0f}% "
                            f"(threshold {weak_link_threshold:.0f}%)."
                        ),
                        meta_data={
                            "link_quality_percent": weakest_link,
                            "threshold_percent": weak_link_threshold,
                            "rc_quality_percent": telemetry.link.rc_quality_pct,
                        },
                    )
                )

        wind_speed = self._to_float(telemetry.wind.speed_mps)
        high_wind_threshold = float(settings.alerts_high_wind_mps or 12.0)
        if wind_speed is not None and wind_speed >= high_wind_threshold:
            signals.append(
                AlertSignal(
                    rule_type="high_wind",
                    dedupe_key="drone.high_wind",
                    source="drone",
                    severity="high",
                    title="High Wind",
                    message=(
                        f"Wind speed reached {wind_speed:.1f} m/s "
                        f"(threshold {high_wind_threshold:.1f} m/s)."
                    ),
                    meta_data={
                        "wind_speed_mps": wind_speed,
                        "threshold_mps": high_wind_threshold,
                        "wind_direction_deg": self._to_float(telemetry.wind.direction_deg),
                    },
                )
            )

        geofence_id = settings.alerts_operation_geofence_id
        lat = self._to_float(telemetry.position.lat)
        lon = self._to_float(telemetry.position.lon)
        if (
            geofence_id
            and lat is not None
            and lon is not None
            and not (abs(lat) < 1e-8 and abs(lon) < 1e-8)
        ):
            geofence = (
                await db.execute(
                    select(Geofence).where(
                        Geofence.id == geofence_id,
                        Geofence.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if geofence:
                polygon = to_shape(geofence.polygon)
                is_inside = polygon.covers(Point(float(lon), float(lat)))
                if not is_inside:
                    signals.append(
                        AlertSignal(
                            rule_type="geofence_breach",
                            dedupe_key=f"drone.geofence_breach.{geofence_id}",
                            source="drone",
                            severity="critical",
                            title="Geofence Breach",
                            message=(
                                f"Drone exited active geofence '{geofence.name}' "
                                f"(id={geofence_id})."
                            ),
                            meta_data={
                                "geofence_id": geofence_id,
                                "geofence_name": geofence.name,
                                "lat": lat,
                                "lon": lon,
                            },
                        )
                    )

        return signals

    async def _evaluate_herd_signals(self, db: AsyncSession) -> list[AlertSignal]:
        signals: list[AlertSignal] = []

        herd_ids = self._parse_int_csv(settings.alerts_monitor_herd_ids)
        max_herds = max(1, int(getattr(settings, "alerts_max_herds_per_cycle", 100)))
        if not herd_ids:
            rows = await db.execute(select(Herd.id).limit(max_herds))
            herd_ids = [int(r[0]) for r in rows.all()]
        else:
            herd_ids = herd_ids[:max_herds]
        if not herd_ids:
            return signals

        threshold = float(settings.alerts_herd_isolation_threshold_m or 250.0)
        try:
            isolation_alerts = await self._risk.isolation_alerts_for_herds(
                db,
                herd_ids=herd_ids,
                threshold_m=threshold,
            )
        except Exception:
            logger.exception("Failed to evaluate herd isolation for herd_ids=%s", herd_ids)
            return signals

        for item in isolation_alerts:
            animal_id = item.get("animal_id")
            collar_id = item.get("collar_id")
            herd_id = int(item.get("herd_id") or 0)
            distance = self._to_float(item.get("distance_to_nearest_m"))
            signals.append(
                AlertSignal(
                    rule_type="herd_isolation",
                    dedupe_key=f"herd.isolation.{herd_id}.{animal_id}",
                    source="herd",
                    severity="high",
                    title="Herd Isolation",
                    message=(
                        f"Animal {collar_id or animal_id} in herd {herd_id} is isolated by "
                        f"{(distance or 0.0):.0f}m (threshold {threshold:.0f}m)."
                    ),
                    meta_data={
                        "herd_id": herd_id,
                        "animal_id": animal_id,
                        "collar_id": collar_id,
                        "distance_to_nearest_m": distance,
                        "threshold_m": threshold,
                        "lat": item.get("lat"),
                        "lon": item.get("lon"),
                    },
                )
            )

        return signals

    async def _emit_in_app_event(
        self,
        *,
        action: str,
        payload: AlertSnapshotV1,
        alert_id: int,
    ) -> None:
        if not settings.alerts_route_in_app:
            return

        status = "sent"
        error_msg = None
        try:
            active_runtime = await mission_runtime_store.get_active_context()
            envelope = AlertEventEnvelopeV1(
                mission_runtime_id=getattr(active_runtime, "client_flight_id", None),
                db_flight_id=getattr(active_runtime, "db_flight_id", None),
                sequence=next_runtime_sequence(
                    getattr(active_runtime, "client_flight_id", None),
                    "alerts.engine",
                ),
                emitted_at=utc_now(),
                source="alerts.engine",
                mission=mission_context_from_runtime(active_runtime),
                payload=AlertEventPayloadV1(action=action, alert=payload),
            )
            await telemetry_manager.broadcast(envelope.to_legacy_websocket_message())
        except Exception as exc:
            status = "failed"
            error_msg = str(exc)
            logger.warning("Failed to emit in-app alert event: %s", exc)

        await self._record_deliveries(
            alert_id,
            [
                {
                    "channel": "in_app",
                    "destination": "websocket",
                    "status": status,
                    "payload": {"action": action},
                    "error": error_msg,
                }
            ],
        )

    async def _record_deliveries(self, alert_id: int, deliveries: list[dict]) -> None:
        if not deliveries:
            return
        async with Session() as db:
            for delivery in deliveries:
                await self._repo.record_delivery(
                    db,
                    alert_id=alert_id,
                    channel=delivery.get("channel", "unknown"),
                    destination=delivery.get("destination"),
                    status=delivery.get("status", "failed"),
                    payload=delivery.get("payload") or {},
                    provider_message_id=delivery.get("provider_message_id"),
                    error=delivery.get("error"),
                )
            await db.commit()

    @staticmethod
    def _dig(source: dict[str, Any], *keys: str) -> Any:
        current: Any = source
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if v != v:  # NaN guard
            return None
        return v

    @staticmethod
    def _parse_int_csv(value: str) -> list[int]:
        out: list[int] = []
        for token in parse_delimited_tokens(value):
            try:
                out.append(int(token))
            except ValueError:
                continue
        return list(dict.fromkeys(out))


alert_engine = AlertEngine()
