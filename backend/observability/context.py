"""Request/job correlation context propagated through logs and traces."""

from __future__ import annotations

import contextvars
import uuid
from typing import Any

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "observability_request_id", default=None
)
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "observability_correlation_id", default=None
)
_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "observability_job_id", default=None
)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str | None) -> contextvars.Token[str | None]:
    return _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def set_correlation_id(value: str | None) -> contextvars.Token[str | None]:
    return _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_job_id(value: str | None) -> contextvars.Token[str | None]:
    return _job_id.set(value)


def get_job_id() -> str | None:
    return _job_id.get()


def log_context_fields() -> dict[str, str]:
    fields: dict[str, str] = {}
    request_id = get_request_id()
    correlation_id = get_correlation_id()
    job_id = get_job_id()
    if request_id:
        fields["request_id"] = request_id
    if correlation_id:
        fields["correlation_id"] = correlation_id
    if job_id:
        fields["job_id"] = job_id
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        context = span.get_span_context()
        if context.is_valid:
            fields["trace_id"] = format(context.trace_id, "032x")
            fields["span_id"] = format(context.span_id, "016x")
    except Exception:
        pass
    return fields


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    _request_id.reset(token)


def reset_correlation_id(token: contextvars.Token[str | None]) -> None:
    _correlation_id.reset(token)


def reset_job_id(token: contextvars.Token[str | None]) -> None:
    _job_id.reset(token)


def bind_log_context(**fields: Any) -> None:
    if "request_id" in fields and fields["request_id"]:
        set_request_id(str(fields["request_id"]))
    if "correlation_id" in fields and fields["correlation_id"]:
        set_correlation_id(str(fields["correlation_id"]))
    if "job_id" in fields and fields["job_id"]:
        set_job_id(str(fields["job_id"]))
