# Local Observability

This project exports **Prometheus metrics** at `/metrics`, **OpenTelemetry traces** via OTLP, and **structured JSON logs** with `trace_id`, `span_id`, `request_id`, `correlation_id`, and `job_id`.

## Docker Compose (recommended)

Start the application and observability stack together:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile observability up -d
```

| Service    | URL                         |
|-----------|-----------------------------|
| Grafana   | http://localhost:3000 (admin / admin) |
| Prometheus| http://localhost:9090     |
| Tempo API | http://localhost:3200       |
| API metrics | http://localhost:8000/metrics |

Tempo OTLP ingest:

- HTTP: `http://tempo:4318` (from containers) or `http://127.0.0.1:4318` (host)
- gRPC: `http://tempo:4317`

The **Drone Platform Reliability** dashboard is auto-provisioned in Grafana.

## Local dev (Honcho / Makefile)

```bash
OBSERVABILITY_ENABLED=true \
OTEL_SERVICE_NAME=drone-api \
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
OTEL_ENVIRONMENT=local \
make local-dev
```

Disable observability:

```bash
make local-dev-no-observability
```

If Grafana/Prometheus/Tempo are installed via systemd:

```bash
make start-observability-stack
make observability-status
```

## Verify

```bash
curl http://127.0.0.1:8000/metrics | head
curl http://127.0.0.1:9090/-/ready
curl http://127.0.0.1:3200/ready
```

Generate API traffic and confirm `http_requests_total` increases in Prometheus.

## Find a trace in Tempo

1. Open Grafana → **Explore** → datasource **Tempo**.
2. Search `{ resource.service.name = "drone-api" }` or paste a `trace_id` from logs.
3. From the reliability dashboard, open the **Recent API traces** panel.

Logs include `trace_id` for correlation. If Loki is added later, configure a derived field on `trace_id` linking to Tempo.

## Correlate a failed job with its trace

1. Find `job_failed` or `job_dead_lettered` in worker logs (includes `celery_task_id`, `job_name`, `trace_id`).
2. Search Tempo by `trace_id` or filter spans with `job.name`.
3. In Prometheus, check `jobs_failed_total{job_name="..."}` and `job_retries_total`.

## Test queue lag and retry metrics

1. Enqueue a Celery task (e.g. photogrammetry job via API).
2. Observe `queue_lag_seconds` and `queue_depth` on `/metrics` or Grafana.
3. Force a retry (stop worker briefly or use a task that raises once).
4. Confirm `job_retries_total` increments and audit log `job_retried` appears.

## Environment variables

See `backend/.env.example` observability section. Key variables:

| Variable | Purpose |
|----------|---------|
| `OBSERVABILITY_ENABLED` | Master switch for OTLP export |
| `OTEL_SERVICE_NAME` | Service name in traces (`drone-api`, `drone-worker`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Tempo OTLP HTTP base URL |
| `OTEL_ENVIRONMENT` | Deployment environment label |
| `PROMETHEUS_METRICS_ENABLED` | Enable `/metrics` middleware |
| `LOG_FORMAT` | Use `json` for structured logs |

## Audit logs

Structured audit events are emitted on the `audit` logger for job lifecycle, database failures, and external API failures. Fields: `event_name`, `actor_type`, `action`, `resource_type`, `result`, `trace_id`, `request_id`, `correlation_id`.
