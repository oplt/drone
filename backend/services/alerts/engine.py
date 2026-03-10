from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Dict, List

import httpx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import Geofence, Herd
from backend.db.repository.alerts_repo import AlertRepository
from backend.db.session import Session
from backend.messaging.websocket import telemetry_manager
from backend.schemas.alerts import OperationalAlertOut
from backend.services.animal_farm.risk_engine import RiskEngine

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
    meta_data: Dict[str, Any]


class AlertEngine:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._repo = AlertRepository()
        self._risk = RiskEngine()

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
            except Exception:
                logger.exception("Operational alert evaluation failed")

            interval = max(2, int(settings.alerts_check_interval_sec or 5))
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.2, interval - elapsed))
        logger.info("Operational alert engine loop stopped")

    async def evaluate_once(self) -> None:
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

            events: list[tuple[str, dict, int]] = []
            notify_queue: list[tuple[dict, int]] = []

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
                    # ✅ Serialize while session is open
                    payload = OperationalAlertOut.model_validate(created).model_dump(mode="json")
                    events.append(("created", payload, created.id))
                    notify_queue.append((payload, created.id))
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
                        # ✅ Serialize while session is open
                        payload = OperationalAlertOut.model_validate(updated).model_dump(mode="json")
                        events.append(("updated", payload, updated.id))
                        notify_queue.append((payload, updated.id))

            for dedupe_key, active in active_by_key.items():
                if dedupe_key in signal_by_key:
                    continue
                resolved = await self._repo.resolve_alert(db, alert=active, now=now)
                # ✅ Force refresh the object to load all attributes while session is open
                await db.refresh(resolved)
                payload = OperationalAlertOut.model_validate(resolved).model_dump(mode="json")
                events.append(("resolved", payload, resolved.id))

            await db.commit()

        # ✅ Now we only use the serialized dictionaries (payloads) after session is closed
        for action, payload, alert_id in events:
            await self._emit_in_app_event(action=action, payload=payload, alert_id=alert_id)

        for payload, alert_id in notify_queue:
            await self._route_external_notifications(payload=payload, alert_id=alert_id)

    async def _evaluate_signals(self, db: AsyncSession) -> list[AlertSignal]:
        telemetry = telemetry_manager.last_telemetry or {}
        signals: list[AlertSignal] = []
        signals.extend(await self._evaluate_drone_signals(db, telemetry))
        signals.extend(await self._evaluate_herd_signals(db))
        return signals

    async def _evaluate_drone_signals(
        self,
        db: AsyncSession,
        telemetry: Dict[str, Any],
    ) -> list[AlertSignal]:
        signals: list[AlertSignal] = []
        telemetry_ts = self._to_float(telemetry.get("timestamp"))
        if telemetry_ts is None or telemetry_ts <= 0:
            return signals

        battery_remaining = self._to_float(
            self._dig(telemetry, "battery", "remaining"),
        )
        low_battery_threshold = float(settings.alerts_low_battery_percent or 25.0)
        if battery_remaining is not None and battery_remaining >= 0 and battery_remaining <= low_battery_threshold:
            signals.append(
                AlertSignal(
                    rule_type="low_battery",
                    dedupe_key="drone.low_battery",
                    source="drone",
                    severity="high",
                    title="Low Battery",
                    message=f"Battery dropped to {battery_remaining:.0f}% (threshold {low_battery_threshold:.0f}%).",
                    meta_data={
                        "battery_remaining": battery_remaining,
                        "threshold_percent": low_battery_threshold,
                    },
                )
            )

        link_values = [
            self._to_float(self._dig(telemetry, "link", "rc")),
            self._to_float(self._dig(telemetry, "link", "telemetry")),
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
                        message=f"Telemetry link quality degraded to {weakest_link:.0f}% (threshold {weak_link_threshold:.0f}%).",
                        meta_data={
                            "link_quality_percent": weakest_link,
                            "threshold_percent": weak_link_threshold,
                            "rc_quality_percent": valid_link_values[0] if valid_link_values else None,
                        },
                    )
                )

        wind_speed = self._to_float(self._dig(telemetry, "wind", "speed"))
        high_wind_threshold = float(settings.alerts_high_wind_mps or 12.0)
        if wind_speed is not None and wind_speed >= high_wind_threshold:
            signals.append(
                AlertSignal(
                    rule_type="high_wind",
                    dedupe_key="drone.high_wind",
                    source="drone",
                    severity="high",
                    title="High Wind",
                    message=f"Wind speed reached {wind_speed:.1f} m/s (threshold {high_wind_threshold:.1f} m/s).",
                    meta_data={
                        "wind_speed_mps": wind_speed,
                        "threshold_mps": high_wind_threshold,
                        "wind_direction_deg": self._to_float(self._dig(telemetry, "wind", "direction")),
                    },
                )
            )

        geofence_id = settings.alerts_operation_geofence_id
        lat = self._to_float(self._dig(telemetry, "position", "lat"))
        lon = self._to_float(self._dig(telemetry, "position", "lon"))
        if geofence_id and lat is not None and lon is not None and not (abs(lat) < 1e-8 and abs(lon) < 1e-8):
            geofence = (
                await db.execute(
                    select(Geofence).where(
                        Geofence.id == geofence_id,
                        Geofence.is_active == True,
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
                            message=f"Drone exited active geofence '{geofence.name}' (id={geofence_id}).",
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
        if not herd_ids:
            rows = await db.execute(select(Herd.id))
            herd_ids = [int(r[0]) for r in rows.all()]
        if not herd_ids:
            return signals

        threshold = float(settings.alerts_herd_isolation_threshold_m or 250.0)
        for herd_id in herd_ids:
            try:
                isolation_alerts = await self._risk.isolation_alerts(
                    db,
                    herd_id=herd_id,
                    threshold_m=threshold,
                )
            except Exception:
                logger.exception("Failed to evaluate herd isolation for herd_id=%s", herd_id)
                continue

            for item in isolation_alerts:
                animal_id = item.get("animal_id")
                collar_id = item.get("collar_id")
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

    async def _emit_in_app_event(self, *, action: str, payload: dict, alert_id: int) -> None:
        if not settings.alerts_route_in_app:
            return

        status = "sent"
        error_msg = None
        try:
            await telemetry_manager.broadcast(
                {
                    "type": "alert_event",
                    "action": action,
                    "alert": payload,
                }
            )
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

    async def _route_external_notifications(self, *, payload: dict, alert_id: int) -> None:
        deliveries: list[dict] = []

        if settings.alerts_route_email:
            deliveries.extend(await self._send_email_notification(payload))
        if settings.alerts_route_sms:
            deliveries.extend(await self._send_sms_notification(payload))

        if deliveries:
            await self._record_deliveries(alert_id, deliveries)

    async def _send_email_notification(self, alert_payload: dict) -> list[dict]:
        recipients = self._parse_csv(settings.alerts_email_recipients)
        smtp_host = (settings.alerts_smtp_host or "").strip()
        sender = (settings.alerts_smtp_from or "").strip()
        if not recipients:
            return [
                {
                    "channel": "email",
                    "destination": None,
                    "status": "skipped",
                    "payload": {"reason": "no_recipients"},
                }
            ]
        if not smtp_host or not sender:
            return [
                {
                    "channel": "email",
                    "destination": ",".join(recipients),
                    "status": "skipped",
                    "payload": {"reason": "smtp_not_configured"},
                }
            ]

        subject = f"[Drone Alert][{str(alert_payload.get('severity', 'info')).upper()}] {alert_payload.get('title', 'Operational alert')}"
        body = "\n".join(
            [
                f"Rule: {alert_payload.get('rule_type')}",
                f"Severity: {alert_payload.get('severity')}",
                f"Status: {alert_payload.get('status')}",
                f"Message: {alert_payload.get('message')}",
                "",
                "Metadata:",
                json.dumps(alert_payload.get("meta_data", {}), indent=2, sort_keys=True),
            ]
        )

        try:
            await asyncio.to_thread(
                self._send_email_sync,
                subject,
                body,
                sender,
                recipients,
            )
            return [
                {
                    "channel": "email",
                    "destination": recipient,
                    "status": "sent",
                    "payload": {"subject": subject},
                }
                for recipient in recipients
            ]
        except Exception as exc:
            return [
                {
                    "channel": "email",
                    "destination": recipient,
                    "status": "failed",
                    "payload": {"subject": subject},
                    "error": str(exc),
                }
                for recipient in recipients
            ]

    def _send_email_sync(
        self,
        subject: str,
        body: str,
        sender: str,
        recipients: list[str],
    ) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)

        host = settings.alerts_smtp_host
        port = int(settings.alerts_smtp_port or 587)
        user = (settings.alerts_smtp_user or "").strip()
        password = settings.alerts_smtp_password or ""
        use_tls = bool(settings.alerts_smtp_use_tls)

        with smtplib.SMTP(host=host, port=port, timeout=10) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls()
                smtp.ehlo()
            if user:
                smtp.login(user=user, password=password)
            smtp.send_message(msg)

    async def _send_sms_notification(self, alert_payload: dict) -> list[dict]:
        recipients = self._parse_csv(settings.alerts_sms_recipients)
        account_sid = (settings.alerts_twilio_account_sid or "").strip()
        auth_token = settings.alerts_twilio_auth_token or ""
        sender = (settings.alerts_twilio_from_number or "").strip()

        if not recipients:
            return [
                {
                    "channel": "sms",
                    "destination": None,
                    "status": "skipped",
                    "payload": {"reason": "no_recipients"},
                }
            ]
        if not account_sid or not auth_token or not sender:
            return [
                {
                    "channel": "sms",
                    "destination": ",".join(recipients),
                    "status": "skipped",
                    "payload": {"reason": "twilio_not_configured"},
                }
            ]

        body = (
            f"[Drone Alert] {str(alert_payload.get('severity', 'info')).upper()} "
            f"{alert_payload.get('title')}: {alert_payload.get('message')}"
        )

        deliveries: list[dict] = []
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        async with httpx.AsyncClient(timeout=12.0) as client:
            for recipient in recipients:
                try:
                    response = await client.post(
                        url,
                        auth=(account_sid, auth_token),
                        data={
                            "From": sender,
                            "To": recipient,
                            "Body": body,
                        },
                    )
                    if response.is_success:
                        response_json = response.json()
                        deliveries.append(
                            {
                                "channel": "sms",
                                "destination": recipient,
                                "status": "sent",
                                "provider_message_id": response_json.get("sid"),
                                "payload": {"twilio_status": response_json.get("status")},
                            }
                        )
                    else:
                        deliveries.append(
                            {
                                "channel": "sms",
                                "destination": recipient,
                                "status": "failed",
                                "payload": {"status_code": response.status_code},
                                "error": response.text[:500],
                            }
                        )
                except Exception as exc:
                    deliveries.append(
                        {
                            "channel": "sms",
                            "destination": recipient,
                            "status": "failed",
                            "payload": {},
                            "error": str(exc),
                        }
                    )
        return deliveries

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
    def _dig(source: Dict[str, Any], *keys: str) -> Any:
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
    def _parse_csv(value: str) -> list[str]:
        if not value:
            return []
        parts: list[str] = []
        for chunk in value.replace(";", ",").replace(" ", ",").split(","):
            token = chunk.strip()
            if token:
                parts.append(token)
        return list(dict.fromkeys(parts))

    @staticmethod
    def _parse_int_csv(value: str) -> list[int]:
        out: list[int] = []
        for token in AlertEngine._parse_csv(value):
            try:
                out.append(int(token))
            except ValueError:
                continue
        return list(dict.fromkeys(out))


alert_engine = AlertEngine()
