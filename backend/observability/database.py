"""Database instrumentation: OpenTelemetry spans and Prometheus pool metrics."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.observability import prometheus_metrics
from backend.observability.audit import emit_audit_event
from backend.observability.errors import normalize_error_type

logger = logging.getLogger(__name__)
_INSTRUMENTED = False


def instrument_database(engine: AsyncEngine) -> None:
    global _INSTRUMENTED
    if _INSTRUMENTED:
        return
    sync_engine = getattr(engine, "sync_engine", None)
    if sync_engine is not None:
        _register_query_listeners(sync_engine)
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        if sync_engine is not None:
            SQLAlchemyInstrumentor().instrument(
                engine=sync_engine,
                enable_commenter=False,
                commenter_options={},
            )
            logger.info("SQLAlchemy OpenTelemetry instrumentation enabled")
    except Exception as exc:
        logger.debug("SQLAlchemy instrumentation skipped: %s", exc)
    _INSTRUMENTED = True


def _register_query_listeners(sync_engine: Any) -> None:
    from sqlalchemy import event

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        conn.info["obs_query_started"] = time.perf_counter()
        conn.info["obs_query_operation"] = _statement_operation(statement)

    @event.listens_for(sync_engine, "handle_error")
    def _handle_error(exception_context: Any) -> None:
        operation = _statement_operation(
            str(getattr(exception_context, "statement", "") or "query")
        )
        exc = getattr(exception_context, "original_exception", None) or getattr(
            exception_context, "sqlalchemy_exception", None
        )
        if isinstance(exc, BaseException):
            record_db_error(operation, exc)

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        started = conn.info.pop("obs_query_started", None)
        if started is None:
            return
        elapsed = time.perf_counter() - started
        operation = conn.info.pop("obs_query_operation", _statement_operation(statement))
        prometheus_metrics.db_query_duration_seconds.labels(
            operation=operation,
            table="unknown",
        ).observe(elapsed)


def _statement_operation(statement: str) -> str:
    head = statement.strip().split(None, 1)[0].upper() if statement.strip() else "QUERY"
    if head in {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"}:
        return head.lower()
    return "query"


def refresh_pool_metrics(engine: AsyncEngine) -> None:
    try:
        pool = engine.sync_engine.pool
        prometheus_metrics.db_pool_active_connections.set(pool.checkedout())
        prometheus_metrics.db_pool_idle_connections.set(pool.checkedin())
    except Exception:
        pass


def record_db_error(operation: str, exc: BaseException) -> None:
    error_type = normalize_error_type(exc)
    prometheus_metrics.db_errors_total.labels(operation=operation, error_type=error_type).inc()
    if error_type in {"connection_error", "operational_error"} or isinstance(exc, ConnectionError):
        prometheus_metrics.db_connection_errors_total.inc()
    emit_audit_event(
        event_name="database_write_failed" if operation == "write" else "database_error",
        action=operation,
        resource_type="database",
        result="failure",
        error_type=error_type,
        reason=error_type,
    )


@asynccontextmanager
async def observed_db_operation(
    operation: str,
    table: str = "unknown",
) -> AsyncGenerator[None, None]:
    """Wrap a DB operation with span, latency histogram, and error metrics."""

    started = time.perf_counter()
    span_cm: Any = None
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("drone.database")
        span_cm = tracer.start_as_current_span(
            f"db.{operation}",
            attributes={
                "db.system": "postgresql",
                "db.operation": operation,
                "db.sql.table": table,
            },
        )
        span_cm.__enter__()
        yield
    except Exception as exc:
        record_db_error(operation, exc)
        if span_cm is not None:
            try:
                from opentelemetry import trace
                from opentelemetry.trace import Status, StatusCode

                span = trace.get_current_span()
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, normalize_error_type(exc)))
            except Exception:
                pass
        raise
    finally:
        elapsed = time.perf_counter() - started
        prometheus_metrics.db_query_duration_seconds.labels(
            operation=operation, table=table
        ).observe(elapsed)
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception:
                pass
