from __future__ import annotations

import asyncio
import json
import smtplib
from email.message import EmailMessage

import httpx

from backend.core.config.runtime import settings
from backend.core.database.session import Session

from .recipient_parsing import parse_delimited_tokens
from .repository import AlertRepository


class AlertNotificationJob:
    def __init__(self, repository: AlertRepository | None = None) -> None:
        self.repository = repository or AlertRepository()

    async def run(self, *, alert_id: int, payload: dict, idempotency_key: str) -> None:
        deliveries: list[dict] = []
        if settings.alerts_route_email:
            deliveries.extend(await self._send_email(payload))
        if settings.alerts_route_sms:
            deliveries.extend(await self._send_sms(payload))
        if not deliveries:
            return
        async with Session() as db:
            for delivery in deliveries:
                await self.repository.record_delivery(
                    db,
                    alert_id=alert_id,
                    channel=delivery["channel"],
                    destination=delivery.get("destination"),
                    status=delivery["status"],
                    payload=delivery.get("payload") or {},
                    provider_message_id=delivery.get("provider_message_id"),
                    error=delivery.get("error"),
                    idempotency_key=(
                        f"{idempotency_key}:{delivery['channel']}:"
                        f"{delivery.get('destination') or 'none'}"
                    ),
                )
            await db.commit()

    async def _send_email(self, payload: dict) -> list[dict]:
        recipients = parse_delimited_tokens(settings.alerts_email_recipients)
        sender = (settings.alerts_smtp_from or "").strip()
        if not recipients or not settings.alerts_smtp_host or not sender:
            return [_skipped("email", ",".join(recipients) or None, "smtp_not_configured")]
        subject = (
            f"[Drone Alert][{str(payload.get('severity', 'info')).upper()}] "
            f"{payload.get('title', 'Operational alert')}"
        )
        body = "\n".join(
            [
                f"Rule: {payload.get('rule_type')}",
                f"Severity: {payload.get('severity')}",
                f"Status: {payload.get('status')}",
                f"Message: {payload.get('message')}",
                json.dumps(payload.get("meta_data", {}), indent=2, sort_keys=True),
            ]
        )
        try:
            await asyncio.to_thread(self._send_email_sync, subject, body, sender, recipients)
            return [_sent("email", recipient, {"subject": subject}) for recipient in recipients]
        except Exception as exc:
            return [_failed("email", recipient, str(exc)) for recipient in recipients]

    @staticmethod
    def _send_email_sync(subject: str, body: str, sender: str, recipients: list[str]) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        with smtplib.SMTP(
            host=settings.alerts_smtp_host,
            port=int(settings.alerts_smtp_port or 587),
            timeout=10,
        ) as smtp:
            smtp.ehlo()
            if settings.alerts_smtp_use_tls:
                smtp.starttls()
                smtp.ehlo()
            if settings.alerts_smtp_user:
                smtp.login(user=settings.alerts_smtp_user, password=settings.alerts_smtp_password)
            smtp.send_message(message)

    async def _send_sms(self, payload: dict) -> list[dict]:
        recipients = parse_delimited_tokens(settings.alerts_sms_recipients)
        sid = (settings.alerts_twilio_account_sid or "").strip()
        token = settings.alerts_twilio_auth_token or ""
        sender = (settings.alerts_twilio_from_number or "").strip()
        if not recipients or not sid or not token or not sender:
            return [_skipped("sms", ",".join(recipients) or None, "twilio_not_configured")]
        body = (
            f"[Drone Alert] {str(payload.get('severity', 'info')).upper()} "
            f"{payload.get('title')}: {payload.get('message')}"
        )
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        deliveries: list[dict] = []
        async with httpx.AsyncClient(timeout=12.0) as client:
            for recipient in recipients:
                try:
                    response = await client.post(
                        url, auth=(sid, token), data={"From": sender, "To": recipient, "Body": body}
                    )
                    if response.is_success:
                        data = response.json()
                        deliveries.append(
                            _sent(
                                "sms",
                                recipient,
                                {"twilio_status": data.get("status")},
                                data.get("sid"),
                            )
                        )
                    else:
                        deliveries.append(_failed("sms", recipient, response.text[:500]))
                except Exception as exc:
                    deliveries.append(_failed("sms", recipient, str(exc)))
        return deliveries


def _skipped(channel: str, destination: str | None, reason: str) -> dict:
    return {
        "channel": channel,
        "destination": destination,
        "status": "skipped",
        "payload": {"reason": reason},
    }


def _sent(channel: str, destination: str, payload: dict, message_id: str | None = None) -> dict:
    return {
        "channel": channel,
        "destination": destination,
        "status": "sent",
        "payload": payload,
        "provider_message_id": message_id,
    }


def _failed(channel: str, destination: str, error: str) -> dict:
    return {"channel": channel, "destination": destination, "status": "failed", "error": error}
