"""Stable structured agriculture lifecycle events."""

import json
import logging
from typing import Any, Literal

logger = logging.getLogger("agriculture.events")
AgricultureEventName = Literal[
    "flight_started", "telemetry_gap", "recording_started", "recording_stopped",
    "ingest_completed", "quality_completed", "analysis_started", "analysis_progress",
    "observation_reviewed", "export_ready",
]


def emit_agriculture_event(name: AgricultureEventName, *, flight_id: str | None = None, **payload: Any) -> None:
    event = {"type": "agriculture_event", "name": name, "event": name, "domain": "agriculture", "flight_id": flight_id, **payload}
    logger.info("agriculture_event %s", json.dumps(event, sort_keys=True, default=str))
