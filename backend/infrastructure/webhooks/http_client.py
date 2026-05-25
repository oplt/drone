from __future__ import annotations

import hmac
import json
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class WebhookResponse:
    status_code: int
    success: bool


class HttpWebhookSender:
    async def send(
        self,
        *,
        url: str,
        secret: str,
        event_type: str,
        payload: dict,
        timeout_s: float,
    ) -> WebhookResponse:
        body = json.dumps(payload, default=str).encode()
        signature = hmac.new(secret.encode(), body, "sha256").hexdigest()
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": f"sha256={signature}",
                    "X-Event-Type": event_type,
                },
            )
        return WebhookResponse(status_code=response.status_code, success=response.is_success)
