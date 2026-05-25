import asyncio
import json
from typing import Any, cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from backend.core.errors.handlers import (
    ApiError,
    RequestIDMiddleware,
    api_error_handler,
    http_exception_handler,
    register_error_handlers,
    unhandled_exception_handler,
    validation_error_handler,
)


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": headers or [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )


def _body(response: Response) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(response.body))


def test_registers_error_handlers() -> None:
    app = FastAPI()

    register_error_handlers(app)

    assert ApiError in app.exception_handlers
    assert RequestValidationError in app.exception_handlers


def test_request_id_middleware_replaces_unsafe_header() -> None:
    async def call_next(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        return None

    middleware = RequestIDMiddleware(app)
    response = asyncio.run(
        middleware.dispatch(_request([(b"x-request-id", b"unsafe\nheader")]), call_next)
    )

    assert response.headers["X-Request-ID"] != "unsafe\nheader"
    assert "\n" not in response.headers["X-Request-ID"]


def test_http_errors_use_stable_envelope() -> None:
    response = asyncio.run(
        http_exception_handler(_request(), HTTPException(404, "Mission not found"))
    )

    assert response.status_code == 404
    assert _body(response) == {
        "error": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "Mission not found",
            "details": {},
        }
    }


def test_internal_http_error_does_not_leak_detail() -> None:
    response = asyncio.run(
        http_exception_handler(_request(), HTTPException(500, "database password leaked"))
    )

    assert response.status_code == 500
    assert _body(response)["error"]["message"] == "Internal server error"
    assert b"password" not in response.body


def test_application_errors_keep_machine_readable_code() -> None:
    response = asyncio.run(
        api_error_handler(
            _request(),
            ApiError(409, "MISSION_ALREADY_RUNNING", "Mission already running"),
        )
    )

    assert response.status_code == 409
    assert _body(response)["error"]["code"] == "MISSION_ALREADY_RUNNING"


def test_validation_errors_use_stable_envelope() -> None:
    error = RequestValidationError(
        [
            {
                "type": "int_parsing",
                "loc": ("path", "item_id"),
                "msg": "Invalid integer",
                "input": "x",
            }
        ]
    )
    response = asyncio.run(validation_error_handler(_request(), error))

    assert response.status_code == 422
    body = _body(response)["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Request validation failed"
    assert body["details"]["errors"]


def test_unhandled_errors_do_not_leak_detail() -> None:
    response = asyncio.run(
        unhandled_exception_handler(_request(), RuntimeError("private implementation error"))
    )

    assert response.status_code == 500
    assert _body(response)["error"]["code"] == "INTERNAL_ERROR"
    assert b"private implementation" not in response.body
