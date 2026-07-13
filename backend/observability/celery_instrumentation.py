"""Celery task instrumentation: traces, metrics, audit logs, queue lag."""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.observability import prometheus_metrics
from backend.observability.audit import emit_audit_event
from backend.observability.context import bind_log_context, set_job_id
from backend.observability.errors import normalize_error_type

logger = logging.getLogger(__name__)

_ENQUEUE_TS_HEADER = "x-observability-enqueue-ts"
_CORRELATION_HEADER = "x-correlation-id"
_REQUEST_ID_HEADER = "x-request-id"
_TASK_STATE: dict[str, dict[str, Any]] = {}
_INSTRUMENTED = False
_BEAT_SCHEDULER_NAMES = {
    "backend.tasks.scheduling_tasks.check_due_templates": "check-due-templates",
    "backend.tasks.outbox_tasks.publish_pending_outbox": "publish-pending-outbox",
    "backend.tasks.webhook_tasks.deliver_pending_webhooks": "deliver-pending-webhooks",
}
_LAST_SCHEDULER_RUN: dict[str, float] = {}


def _task_name(task: Any) -> str:
    name = getattr(task, "name", None) or getattr(getattr(task, "request", None), "task", None)
    return str(name or "unknown")


def _task_queue(task: Any) -> str:
    delivery = getattr(getattr(task, "request", None), "delivery_info", None) or {}
    routing_key = delivery.get("routing_key")
    if routing_key:
        return str(routing_key)
    return str(getattr(task, "queue", None) or "default")


def _headers(task: Any) -> dict[str, Any]:
    request = getattr(task, "request", None)
    if request is None:
        return {}
    return dict(getattr(request, "headers", None) or {})


def _inject_publish_context(headers: dict[str, Any] | None, **extra: Any) -> None:
    if headers is None:
        return
    headers[_ENQUEUE_TS_HEADER] = str(time.time())
    try:
        from opentelemetry.propagate import inject

        inject(headers)
    except Exception:
        pass
    try:
        from backend.observability.context import get_correlation_id, get_request_id

        request_id = get_request_id()
        correlation_id = get_correlation_id()
        if request_id:
            headers[_REQUEST_ID_HEADER] = request_id
        if correlation_id:
            headers[_CORRELATION_HEADER] = correlation_id
    except Exception:
        pass
    for key, value in extra.items():
        if value is not None:
            headers[key] = str(value)


def _extract_worker_context(headers: dict[str, Any]) -> Any | None:
    try:
        from opentelemetry.context import attach
        from opentelemetry.propagate import extract

        return attach(extract(headers))
    except Exception:
        return None


def _start_job_span(task: Any, job_name: str, queue: str) -> Any:
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("drone.celery")
        return tracer.start_as_current_span(
            f"job.execute {job_name}",
            attributes={
                "job.name": job_name,
                "job.id": str(getattr(getattr(task, "request", None), "id", "")),
                "queue.name": queue,
                "retry.count": int(getattr(getattr(task, "request", None), "retries", 0) or 0),
            },
        )
    except Exception:
        from contextlib import nullcontext

        return nullcontext()


def _log_job_event(event_name: str, task: Any, **extra: Any) -> None:
    request = getattr(task, "request", None)
    job_name = _task_name(task)
    queue = _task_queue(task)
    payload = {
        "event_name": event_name,
        "job_name": job_name,
        "queue": queue,
        "celery_task_id": getattr(request, "id", None),
        "retry_count": int(getattr(request, "retries", 0) or 0),
        **extra,
    }
    logger.info(event_name, extra={k: v for k, v in payload.items() if v is not None})


def instrument_celery(celery_app: Any) -> None:
    global _INSTRUMENTED
    if _INSTRUMENTED:
        return

    from celery import signals

    @signals.before_task_publish.connect
    def on_before_task_publish(sender: str | None = None, headers: dict | None = None, **kwargs: Any) -> None:
        _inject_publish_context(headers)
        job_name = str(sender or "unknown")
        queue = str((kwargs.get("routing_key") or kwargs.get("queue") or "default"))
        emit_audit_event(
            event_name="job_enqueued",
            action="enqueue",
            resource_type="job",
            resource_id=job_name,
            result="success",
            extra={"queue": queue},
        )
        logger.info(
            "job_enqueued",
            extra={"job_name": job_name, "queue": queue},
        )

    @signals.task_prerun.connect
    def on_task_prerun(task_id: str, task: Any, *args: Any, **kwargs: Any) -> None:
        headers = _headers(task)
        token = _extract_worker_context(headers)
        job_name = _task_name(task)
        queue = _task_queue(task)
        bind_log_context(
            request_id=headers.get(_REQUEST_ID_HEADER),
            correlation_id=headers.get(_CORRELATION_HEADER),
            job_id=task_id,
            queue=queue,
            task_id=task_id,
        )
        set_job_id(task_id)

        enqueue_raw = headers.get(_ENQUEUE_TS_HEADER)
        if enqueue_raw:
            try:
                lag = max(0.0, time.time() - float(enqueue_raw))
                prometheus_metrics.queue_lag_seconds.labels(queue=queue).observe(lag)
            except (TypeError, ValueError):
                pass

        span_cm = _start_job_span(task, job_name, queue)
        span_cm.__enter__()
        started = time.perf_counter()
        _TASK_STATE[task_id] = {
            "started": started,
            "span_cm": span_cm,
            "otel_token": token,
            "job_name": job_name,
            "queue": queue,
        }
        prometheus_metrics.jobs_started_total.labels(job_name=job_name, queue=queue).inc()
        scheduler_name = _BEAT_SCHEDULER_NAMES.get(job_name)
        if scheduler_name:
            now = time.time()
            last = _LAST_SCHEDULER_RUN.get(scheduler_name)
            if last is not None:
                prometheus_metrics.scheduler_lag_seconds.labels(
                    scheduler_name=scheduler_name
                ).set(max(0.0, now - last))
            _LAST_SCHEDULER_RUN[scheduler_name] = now
            prometheus_metrics.scheduler_runs_total.labels(
                scheduler_name=scheduler_name
            ).inc()
        _log_job_event("job_started", task)

    @signals.task_postrun.connect
    def on_task_postrun(task_id: str, task: Any, retval: Any, state: str, **kwargs: Any) -> None:
        state_info = _TASK_STATE.pop(task_id, None)
        if not state_info:
            return
        elapsed = time.perf_counter() - state_info["started"]
        job_name = state_info["job_name"]
        queue = state_info["queue"]
        prometheus_metrics.job_duration_seconds.labels(job_name=job_name, queue=queue).observe(elapsed)
        prometheus_metrics.celery_task_duration_seconds.labels(
            task_name=job_name, status=state.lower()
        ).observe(elapsed)

        if state == "SUCCESS":
            prometheus_metrics.jobs_completed_total.labels(job_name=job_name, queue=queue).inc()
            emit_audit_event(
                event_name="job_completed",
                action="execute",
                resource_type="job",
                resource_id=task_id,
                result="success",
                extra={"job_name": job_name, "queue": queue},
            )
            _log_job_event("job_completed", task, duration_seconds=round(elapsed, 4))
        elif state in {"FAILURE", "REVOKED"}:
            error_type = "revoked" if state == "REVOKED" else "task_failure"
            prometheus_metrics.jobs_failed_total.labels(
                job_name=job_name, queue=queue, error_type=error_type
            ).inc()
            emit_audit_event(
                event_name="job_failed",
                action="execute",
                resource_type="job",
                resource_id=task_id,
                result="failure",
                error_type=error_type,
                extra={"job_name": job_name, "queue": queue},
            )
            _log_job_event("job_failed", task, error_type=error_type)

        span_cm = state_info.get("span_cm")
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception:
                pass
        token = state_info.get("otel_token")
        if token is not None:
            try:
                from opentelemetry.context import detach

                detach(token)
            except Exception:
                pass

    @signals.task_retry.connect
    def on_task_retry(request: Any, reason: Any, einfo: Any, **kwargs: Any) -> None:
        job_name = str(getattr(request, "task", None) or "unknown")
        queue = str(getattr(request, "delivery_info", {}).get("routing_key") or "default")
        retry_reason = normalize_error_type(reason if isinstance(reason, BaseException) else None)
        if retry_reason == "unknown" and reason is not None:
            retry_reason = type(reason).__name__
        prometheus_metrics.job_retries_total.labels(
            job_name=job_name, queue=queue, retry_reason=retry_reason
        ).inc()
        prometheus_metrics.retry_count_total.labels(subsystem="celery", reason=retry_reason).inc()
        emit_audit_event(
            event_name="job_retried",
            action="retry",
            resource_type="job",
            resource_id=str(getattr(request, "id", "")),
            result="failure",
            reason=retry_reason,
            extra={"job_name": job_name, "queue": queue},
        )
        logger.warning(
            "job_retried",
            extra={
                "job_name": job_name,
                "queue": queue,
                "retry_reason": retry_reason,
                "celery_task_id": getattr(request, "id", None),
            },
        )

    @signals.task_failure.connect
    def on_task_failure(
        task_id: str,
        exception: BaseException,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        traceback: Any,
        einfo: Any,
        **other: Any,
    ) -> None:
        request = other.get("sender")
        job_name = _task_name(request) if request else "unknown"
        queue = _task_queue(request) if request else "default"
        error_type = normalize_error_type(exception)
        scheduler_name = _BEAT_SCHEDULER_NAMES.get(job_name)
        if scheduler_name:
            prometheus_metrics.scheduler_failures_total.labels(
                scheduler_name=scheduler_name,
                error_type=error_type,
            ).inc()
        retries = int(getattr(getattr(request, "request", None), "retries", 0) or 0)
        max_retries = getattr(request, "max_retries", None) if request else None
        if max_retries is not None and retries >= max_retries:
            prometheus_metrics.job_dead_letter_total.labels(job_name=job_name, queue=queue).inc()
            emit_audit_event(
                event_name="job_dead_lettered",
                action="dead_letter",
                resource_type="job",
                resource_id=task_id,
                result="failure",
                error_type=error_type,
                extra={"job_name": job_name, "queue": queue},
            )
            logger.error(
                "job_dead_lettered",
                extra={
                    "job_name": job_name,
                    "queue": queue,
                    "error_type": error_type,
                    "celery_task_id": task_id,
                },
            )

    _INSTRUMENTED = True
    logger.info("Celery observability instrumentation enabled")
