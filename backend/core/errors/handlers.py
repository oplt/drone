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

from backend.core.logging import emit_app_log, sanitize_log_details

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
    request_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    response_headers = dict(headers or {})
    if request_id:
        response_headers.setdefault("X-Request-ID", request_id)
    return JSONResponse(
        status_code=status_code,
        headers=response_headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details if details is not None else {},
                "request_id": request_id,
            }
        },
    )


def _safe_http_message(status_code: int, detail: Any) -> tuple[str, Any]:
    if status_code >= 500 and status_code not in {503}:
        return "Internal server error", {}
    if isinstance(detail, str):
        return detail, {}
    if isinstance(detail, dict):
        message = str(detail.get("message", "Request failed"))
        details = {key: value for key, value in detail.items() if key != "message"}
        return message, details
    return "Request failed", {}


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(ApiError, exc)
    request_id = getattr(request.state, "request_id", None)
    level = "error" if error.status_code >= 500 else "warn"
    logger.log(
        logging.ERROR if level == "error" else logging.WARNING,
        "API error request_id=%s status=%s code=%s path=%s",
        request_id,
        error.status_code,
        error.code,
        request.url.path,
        extra={
            "request_id": request_id,
            "status_code": error.status_code,
            "error_code": error.code,
            "path": request.url.path,
            "details": sanitize_log_details(error.details),
        },
    )
    await emit_app_log(
        level=level,
        source="api",
        message=error.message,
        details={
            "status_code": error.status_code,
            "code": error.code,
            "path": request.url.path,
        },
        request_id=request_id,
    )
    return _response(
        status_code=error.status_code,
        code=error.code,
        message=error.message,
        details=error.details,
        request_id=request_id,
        headers=error.headers,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    message, details = _safe_http_message(error.status_code, error.detail)
    request_id = getattr(request.state, "request_id", None)
    if error.status_code >= 500:
        logger.error(
            "HTTP exception request_id=%s status=%s path=%s",
            request_id,
            error.status_code,
            request.url.path,
            extra={
                "request_id": request_id,
                "status_code": error.status_code,
                "path": request.url.path,
                "details": sanitize_log_details(details),
            },
        )
        await emit_app_log(
            level="error",
            source="api",
            message=message,
            details={
                "status_code": error.status_code,
                "code": _STATUS_CODES.get(error.status_code, f"HTTP_{error.status_code}"),
                "path": request.url.path,
            },
            request_id=request_id,
        )
    return _response(
        status_code=error.status_code,
        code=_STATUS_CODES.get(error.status_code, f"HTTP_{error.status_code}"),
        message=message,
        details=details,
        request_id=request_id,
        headers=error.headers,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "Request validation failed request_id=%s path=%s error_count=%s",
        request_id,
        request.url.path,
        len(error.errors()),
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "error_count": len(error.errors()),
            "validation_errors": sanitize_log_details(error.errors()),
        },
    )
    await emit_app_log(
        level="warn",
        source="api",
        message="Request validation failed",
        details={
            "status_code": 422,
            "path": request.url.path,
            "error_count": len(error.errors()),
        },
        request_id=request_id,
    )
    return _response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"errors": jsonable_encoder(error.errors())},
        request_id=request_id,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unhandled request exception request_id=%s path=%s type=%s",
        request_id,
        request.url.path,
        type(exc).__name__,
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "exception_type": type(exc).__name__,
        },
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    await emit_app_log(
        level="critical",
        source="api",
        message="Unexpected server error",
        details={
            "status_code": 500,
            "path": request.url.path,
            "exception_type": type(exc).__name__,
        },
        request_id=request_id,
    )
    return _response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Internal server error",
        request_id=request_id,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
