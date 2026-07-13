"""Cheap pre-body limits for multipart upload endpoints."""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class UploadBodyLimitMiddleware:
    """Reject obviously oversized requests before multipart parsing allocates work.

    A missing or malformed Content-Length is allowed; streaming validators still
    enforce the exact file limit while reading the body.
    """

    def __init__(self, app: ASGIApp, *, limits: dict[str, int]) -> None:
        self.app = app
        self.limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        limit = self.limits.get(path)
        if limit is not None:
            headers: dict[bytes, Any] = dict(scope.get("headers") or [])
            raw_length = headers.get(b"content-length")
            try:
                content_length = int(raw_length) if raw_length else None
            except (TypeError, ValueError):
                content_length = None
            if content_length is not None and content_length > limit:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": "Upload exceeds the request size limit.",
                            "details": {},
                        }
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
