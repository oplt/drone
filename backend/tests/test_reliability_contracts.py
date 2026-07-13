from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.types import Message, Receive, Scope, Send

from backend.core.errors.request_limits import UploadBodyLimitMiddleware
from backend.core.retry import retry_delay_seconds


def test_retry_delay_has_exponential_jitter_and_hard_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.core.retry.random.uniform", lambda _low, _high: 1.2)

    assert retry_delay_seconds(attempt=0, base_seconds=10, max_seconds=30) == 12
    assert retry_delay_seconds(attempt=10, base_seconds=10, max_seconds=30) == 30


def test_migration_baseline_is_single_head_and_has_query_indexes() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(Path("backend/alembic.ini")))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1
    index_migration = (
        Path("backend/infrastructure/persistence/alembic/versions/")
        / "t6a2b3c4d5e6_add_request_path_indexes.py"
    )
    text = index_migration.read_text(encoding="utf-8")
    assert "idx_mission_runtime_client_state" in text
    assert "idx_webhook_delivery_endpoint_status_created" in text


def test_upload_body_limit_rejects_declared_oversize() -> None:
    called = False

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    middleware = UploadBodyLimitMiddleware(app, limits={"/upload": 10})
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        messages.append(message)

    asyncio.run(
        middleware(
            {
                "type": "http",
                "path": "/upload",
                "headers": [(b"content-length", b"11")],
            },
            receive,
            send,
        )
    )
    assert called is False
    assert any(message.get("status") == 413 for message in messages)


def test_external_http_failure_closes_span_with_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("opentelemetry")
    from opentelemetry import trace

    from backend.observability import external_http

    class Span:
        error: tuple | None = None

        def __enter__(self) -> Span:
            return self

        def __exit__(self, *args: Any) -> None:
            self.error = args

    span = Span()

    class Tracer:
        def start_as_current_span(self, *_args: Any, **_kwargs: Any) -> Span:
            return span

    class Client:
        async def request(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("upstream unavailable")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(trace, "get_tracer", lambda *_args: Tracer())
    client = external_http.InstrumentedAsyncClient("test")
    client._client = cast(Any, Client())
    try:
        try:
            asyncio.run(client.request("GET", "https://example.test/health"))
        except RuntimeError:
            pass
        assert span.error is not None
        assert span.error[0] is RuntimeError
        assert isinstance(span.error[1], RuntimeError)
    finally:
        asyncio.run(client.aclose())
