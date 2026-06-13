from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

_DRONE_ATTRS = {
    "mission_id": "mission.id",
    "drone_id": "drone.id",
    "flight_id": "flight.id",
    "frame_id": "frame.id",
    "camera_name": "camera.name",
    "ros_topic": "ros.topic",
    "ros_message_type": "ros.message_type",
    "map_id": "map.id",
    "chunk_id": "chunk.id",
    "mavlink_command": "mavlink.command.name",
    "waypoint_id": "waypoint.id",
}


def _attrs(kwargs: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        attr = _DRONE_ATTRS.get(key, key.replace("_", "."))
        if isinstance(value, str | bool | int | float):
            attrs[attr] = value
        else:
            attrs[attr] = str(value)
    return attrs


@contextmanager
def observed_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Create span, attach drone attrs, record failures, then re-raise."""

    try:
        from opentelemetry import trace
        from opentelemetry.trace import Status, StatusCode
    except Exception:
        yield None
        return

    tracer = trace.get_tracer("drone.observability")
    with tracer.start_as_current_span(name, attributes=_attrs(attributes)) as span:
        started = time.monotonic()
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise
        finally:
            span.set_attribute("latency_ms", (time.monotonic() - started) * 1000.0)


def structured_error(
    logger_: logging.Logger,
    message: str,
    exc: BaseException,
    **fields: Any,
) -> None:
    extra = {
        key: value
        for key, value in fields.items()
        if value is not None and isinstance(value, str | bool | int | float)
    }
    extra["error_type"] = type(exc).__name__
    extra["error_message"] = str(exc)[:500]
    logger_.error(message, extra=extra, exc_info=True)
