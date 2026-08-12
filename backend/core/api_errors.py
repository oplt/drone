from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

ERROR_ENVELOPE_VERSION = "1"


@dataclass(slots=True)
class DomainApiError(Exception):
    status_code: int
    code: str
    message: str
    fields: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


def map_domain_exception(exc: Exception, *, domain: str) -> DomainApiError:
    name = type(exc).__name__
    code_prefix = domain.upper()
    fields: dict[str, Any] = {}
    if hasattr(exc, "expected_revision"):
        fields["expected_revision"] = exc.expected_revision  # type: ignore[attr-defined]
    if hasattr(exc, "current_revision"):
        fields["current_revision"] = exc.current_revision  # type: ignore[attr-defined]
    if "NotFound" in name:
        return DomainApiError(404, f"{code_prefix}_NOT_FOUND", str(exc), fields)
    if "Conflict" in name:
        return DomainApiError(409, f"{code_prefix}_CONFLICT", str(exc), fields)
    if "WorkerUnavailable" in name:
        return DomainApiError(
            503,
            f"{code_prefix}_WORKER_UNAVAILABLE",
            str(exc),
            fields,
            retryable=True,
        )
    return DomainApiError(422, f"{code_prefix}_VALIDATION_ERROR", str(exc), fields)


async def domain_api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(DomainApiError, exc)
    trace_id = getattr(request.state, "request_id", None)
    body: dict[str, Any] = {
        "code": error.code,
        "message": error.message,
        "retryable": error.retryable,
    }
    if error.fields:
        body["fields"] = error.fields
    if trace_id:
        body["trace_id"] = trace_id
    return JSONResponse(
        status_code=error.status_code,
        headers={"X-API-Error-Version": ERROR_ENVELOPE_VERSION},
        content=jsonable_encoder({"error": body}),
    )


def register_domain_api_error_handler(app: FastAPI) -> None:
    app.add_exception_handler(DomainApiError, domain_api_error_handler)
