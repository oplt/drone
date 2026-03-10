from __future__ import annotations

import httpx

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional
from backend.messaging.websocket import telemetry_manager
from backend.ml.patrol.models import AnomalyEvent


log = logging.getLogger(__name__)


@dataclass
class PipelineEvent:
    event_type: str
    confidence: float
    location: dict[str, Any] | None
    payload: dict[str, Any]


class EventDispatcher:
    def __init__(self, *, emit_websocket_events: bool = True, duplicate_window_s: float = 10.0, max_events_per_track: int = 8):
        self.emit_websocket_events = emit_websocket_events
        self.duplicate_window_s = float(duplicate_window_s)
        self.max_events_per_track = int(max_events_per_track)
        self._last_sent_at: dict[str, float] = {}
        self._track_event_counts: dict[int, int] = defaultdict(int)

    def _dedupe_key(self, event: PipelineEvent) -> str:
        track_id = event.payload.get("track_id", "na")
        label = event.payload.get("label", "na")
        return f"{event.event_type}:{track_id}:{label}"

    def _allow_emit(self, event: PipelineEvent) -> bool:
        now = time.time()
        key = self._dedupe_key(event)
        previous = self._last_sent_at.get(key)
        if previous is not None and (now - previous) < self.duplicate_window_s:
            return False

        track_id = event.payload.get("track_id")
        if isinstance(track_id, int):
            count = self._track_event_counts[track_id]
            if count >= self.max_events_per_track:
                return False
            self._track_event_counts[track_id] = count + 1

        self._last_sent_at[key] = now
        return True

    async def dispatch(self, event: PipelineEvent) -> None:
        if not self._allow_emit(event):
            return

        if self.emit_websocket_events:
            try:
                await telemetry_manager.broadcast(
                    {
                        "type": "ml_anomaly_event",
                        "event_type": event.event_type,
                        "confidence": event.confidence,
                        "location": event.location,
                        "payload": event.payload,
                    }
                )
            except Exception:
                log.exception("Failed broadcasting ML anomaly event")

    async def emit_system_message(self, message: str) -> None:
        if not self.emit_websocket_events:
            return
        try:
            await telemetry_manager.broadcast({"type": "ml_status", "message": message})
        except Exception:
            log.exception("Failed broadcasting ML status message")



class EventSink:
    def __init__(
            self,
            *,
            mode: str = "http",
            url: Optional[str] = None,
            timeout_s: float = 5.0,
    ) -> None:
        self.mode = str(mode).strip().lower()
        self.url = url
        self.timeout_s = float(timeout_s)

    async def send(self, event: AnomalyEvent) -> None:
        if self.mode == "noop":
            return

        if self.mode != "http":
            raise ValueError(f"Unsupported event sink mode: {self.mode}")

        if not self.url:
            raise ValueError("EventSink url is required when mode='http'")

        payload = {
            "event_type": event.event_type,
            "confidence": event.confidence,
            "location": (
                {"lat": event.location.lat, "lon": event.location.lon}
                if event.location is not None
                else None
            ),
            "payload": event.payload or {},
        }

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(self.url, json=payload)
            resp.raise_for_status()
