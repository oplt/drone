from __future__ import annotations

import logging

from backend.observability.context import get_correlation_id, get_job_id, get_request_id


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        from backend.observability.config import load_config

        config = load_config()
        record.service_name = getattr(record, "service_name", config.service_name)
        record.environment = getattr(record, "environment", config.environment)
        record.request_id = getattr(record, "request_id", get_request_id() or "")
        record.correlation_id = getattr(record, "correlation_id", get_correlation_id() or "")
        record.job_id = getattr(record, "job_id", get_job_id() or "")
        record.otel_trace_id = getattr(record, "otel_trace_id", "")
        record.otel_span_id = getattr(record, "otel_span_id", "")
        record.trace_id = getattr(record, "trace_id", record.otel_trace_id)
        record.span_id = getattr(record, "span_id", record.otel_span_id)
        try:
            from opentelemetry import trace

            context = trace.get_current_span().get_span_context()
            if context.is_valid:
                trace_id = format(context.trace_id, "032x")
                span_id = format(context.span_id, "016x")
                record.otel_trace_id = trace_id
                record.otel_span_id = span_id
                record.trace_id = trace_id
                record.span_id = span_id
        except Exception:
            pass
        return True


def install_trace_context_filter() -> None:
    root = logging.getLogger()
    if not any(isinstance(filter_, TraceContextFilter) for filter_ in root.filters):
        root.addFilter(TraceContextFilter())
    for handler in root.handlers:
        if not any(isinstance(filter_, TraceContextFilter) for filter_ in handler.filters):
            handler.addFilter(TraceContextFilter())
