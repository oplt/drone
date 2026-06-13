# Local Observability

Local dev uses standard Grafana, Prometheus, Tempo, OpenTelemetry, and a
Prometheus-compatible `/metrics` endpoint. Maple is optional and disabled by
default.

## Install

Install Grafana, Tempo, and Prometheus with your package manager, Docker, or
their upstream binaries. The backend does not start these services itself.

Expected local URLs:

- Grafana: `http://127.0.0.1:3000`
- Tempo ready check: `http://127.0.0.1:3200/ready`
- Prometheus ready check: `http://127.0.0.1:9090/-/ready`
- Tempo OTLP/HTTP ingest: `http://127.0.0.1:4318`

## Grafana Datasources

Add a Tempo datasource:

- URL: `http://127.0.0.1:3200`

Add a Prometheus datasource:

- URL: `http://127.0.0.1:9090`

## Run App

```bash
OBSERVABILITY_ENABLED=true \
OTEL_SERVICE_NAME=drone-api \
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
make local-dev
```

No observability:

```bash
make local-dev-no-observability
```

Explicit observability:

```bash
make local-dev-observability
```

## Verify

```bash
curl http://127.0.0.1:3200/ready
curl http://127.0.0.1:9090/-/ready
curl http://127.0.0.1:8000/metrics
make observability-status
```

Prometheus scrape target:

```yaml
scrape_configs:
  - job_name: drone-api
    static_configs:
      - targets: ["127.0.0.1:8000"]
```

Tempo receives traces when it listens on `127.0.0.1:4318` for OTLP/HTTP.
If Tempo, Prometheus, or Grafana are down, the FastAPI app still starts.
