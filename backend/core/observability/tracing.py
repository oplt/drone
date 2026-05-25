"""OpenTelemetry tracing setup."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def setup_tracing(app, engine=None) -> None:  # type: ignore[type-arg]
    from backend.core.config.runtime import settings

    if not settings.otel_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": "drone-api"})
        provider = TracerProvider(resource=resource)

        if settings.otel_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
        else:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            exporter = ConsoleSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        logger.info(
            "OpenTelemetry tracing enabled (endpoint=%s)", settings.otel_endpoint or "console"
        )

        if engine is not None:
            try:
                from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

                SQLAlchemyInstrumentor().instrument(engine=engine)
            except Exception as exc:
                logger.warning("SQLAlchemy OTel instrumentation skipped: %s", exc)

    except ImportError as exc:
        logger.warning("OpenTelemetry packages not installed, tracing disabled: %s", exc)
    except Exception as exc:
        logger.error("Failed to set up OpenTelemetry tracing: %s", exc)
