from __future__ import annotations

import logging


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        from backend.observability.config import load_config

        config = load_config()
        record.service_name = getattr(record, "service_name", config.service_name)
        record.environment = getattr(record, "environment", config.environment)
        record.otel_trace_id = getattr(record, "otel_trace_id", "")
        record.otel_span_id = getattr(record, "otel_span_id", "")
        try:
            from opentelemetry import trace

            context = trace.get_current_span().get_span_context()
            if context.is_valid:
                record.otel_trace_id = format(context.trace_id, "032x")
                record.otel_span_id = format(context.span_id, "016x")
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
