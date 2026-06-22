from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.modules.patrol.vision.config import ml_settings
from backend.modules.patrol.vision.events import EventDispatcher, PipelineEvent

router = APIRouter(prefix="/api", tags=["ml-events"])

_event_dispatcher = EventDispatcher(
    emit_websocket_events=ml_settings.emit_websocket_events,
    duplicate_window_s=ml_settings.max_duplicate_event_s,
    max_events_per_track=ml_settings.max_events_per_track,
)


class MLAnomalyEventIn(BaseModel):
    event_type: str
    confidence: float
    location: dict[str, Any] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/events")
async def ingest_ml_anomaly_event(body: MLAnomalyEventIn) -> dict[str, bool]:
    """Ingest ML anomaly events from the vision pipeline or external integrations."""
    await _event_dispatcher.dispatch(
        PipelineEvent(
            event_type=body.event_type,
            confidence=body.confidence,
            location=body.location,
            payload=body.payload,
        )
    )
    return {"accepted": True}
