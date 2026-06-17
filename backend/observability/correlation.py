"""HTTP middleware for request and correlation identifiers."""

from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from backend.observability.context import (
    bind_log_context,
    get_correlation_id,
    new_correlation_id,
    reset_correlation_id,
    reset_request_id,
    set_correlation_id,
    set_request_id,
)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _valid_id(value: str) -> str | None:
    value = value.strip()
    if _ID_PATTERN.fullmatch(value):
        return value
    return None


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Set request_id and correlation_id on every HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = _valid_id(supplied_request_id) or uuid.uuid4().hex
        request.state.request_id = request_id

        supplied_correlation_id = request.headers.get("X-Correlation-ID", "")
        correlation_id = (
            _valid_id(supplied_correlation_id)
            or getattr(request.state, "correlation_id", None)
            or new_correlation_id()
        )
        request.state.correlation_id = correlation_id

        req_token = set_request_id(request_id)
        corr_token = set_correlation_id(correlation_id)
        bind_log_context(request_id=request_id, correlation_id=correlation_id)

        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            reset_request_id(req_token)
            reset_correlation_id(corr_token)
            if response is not None:
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Correlation-ID"] = correlation_id


def current_correlation_id() -> str | None:
    return get_correlation_id()
