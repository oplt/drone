from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from backend.modules.integrations.webhooks.contracts import VALID_WEBHOOK_EVENTS


class WebhookEndpointCreate(BaseModel):
    url: str
    events: list[str]

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, value: str) -> str:
        if not (value.startswith("https://") or value.startswith("http://")):
            raise ValueError("url must start with https:// or http://")
        return value

    @field_validator("events")
    @classmethod
    def events_must_be_valid(cls, value: list[str]) -> list[str]:
        invalid = set(value) - VALID_WEBHOOK_EVENTS
        if invalid:
            raise ValueError(
                f"Unknown event types: {sorted(invalid)}. Valid: {sorted(VALID_WEBHOOK_EVENTS)}"
            )
        return value


class WebhookEndpointUpdate(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, value: str | None) -> str | None:
        if value is not None and not (value.startswith("https://") or value.startswith("http://")):
            raise ValueError("url must start with https:// or http://")
        return value

    @field_validator("events")
    @classmethod
    def events_must_be_valid(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            invalid = set(value) - VALID_WEBHOOK_EVENTS
            if invalid:
                raise ValueError(
                    f"Unknown event types: {sorted(invalid)}. Valid: {sorted(VALID_WEBHOOK_EVENTS)}"
                )
        return value


class WebhookEndpointOut(BaseModel):
    id: int
    org_id: int | None
    url: str
    events: list[Any]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryOut(BaseModel):
    id: int
    endpoint_id: int
    event_type: str
    status: str
    attempts: int
    last_attempted_at: datetime | None
    next_retry_at: datetime | None
    response_code: int | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
