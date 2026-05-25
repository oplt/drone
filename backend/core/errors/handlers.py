from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    501: "NOT_IMPLEMENTED",
    503: "SERVICE_UNAVAILABLE",
}


@dataclass(slots=True)
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] | None = None


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else str(uuid.uuid4())[:8]
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details if details is not None else {},
            }
        },
    )


def _safe_http_message(status_code: int, detail: Any) -> tuple[str, Any]:
    if status_code >= 500:
        return "Internal server error", {}
    if isinstance(detail, str):
        return detail, {}
    if isinstance(detail, dict):
        message = str(detail.get("message", "Request failed"))
        return message, detail.get("details", {})
    return "Request failed", {}


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(ApiError, exc)
    return _response(
        status_code=error.status_code,
        code=error.code,
        message=error.message,
        details=error.details,
        headers=error.headers,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    message, details = _safe_http_message(error.status_code, error.detail)
    return _response(
        status_code=error.status_code,
        code=_STATUS_CODES.get(error.status_code, f"HTTP_{error.status_code}"),
        message=message,
        details=details,
        headers=error.headers,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    return _response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"errors": jsonable_encoder(error.errors())},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled request exception request_id=%s path=%s type=%s",
        getattr(request.state, "request_id", None),
        request.url.path,
        type(exc).__name__,
    )
    return _response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Internal server error",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
