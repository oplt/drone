# Grafana Observability

The backend emits standard OTLP/HTTP traces, metrics, and logs. That works with Grafana Cloud directly, or with Grafana Alloy as a local OpenTelemetry Collector.

## Grafana Cloud Direct

Use Grafana Cloud's OpenTelemetry connection tile to generate the endpoint and headers. Grafana Cloud expects OTLP plus authentication headers.

Example:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-east-0.grafana.net/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic%20<base64-instance-id-colon-token>"
export OTEL_SERVICE_NAME=drone-api
export APP_ENV=local
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=drone,service.version=local,service.instance.id=$(hostname)"
```

For Python/Grafana Cloud, keep `Basic%20` in the environment value. The backend decodes it to `Basic ` before passing headers to the OTLP exporter.

## Grafana Alloy Local Collector

For production-like setups, send the backend to Alloy, then let Alloy export to Grafana Cloud, Tempo, Loki, and Mimir/Prometheus.

Backend env:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
export OTEL_SERVICE_NAME=drone-api
export APP_ENV=local
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=drone,service.version=local"
```

Minimal Alloy receiver shape:

```alloy
otelcol.receiver.otlp "drone" {
  http {
    endpoint = "0.0.0.0:4318"
  }

  output {
    traces  = [otelcol.exporter.otlp.grafana.input]
    metrics = [otelcol.exporter.otlp.grafana.input]
    logs    = [otelcol.exporter.otlp.grafana.input]
  }
}
```

Use Grafana Cloud's Alloy connection tile for the exporter block; it provides the correct endpoint and auth values.

## What To Look For

Grafana Explore:

- Traces/Tempo: filter `service.name="drone-api"`.
- Logs/Loki: filter by resource labels such as `service_name="drone-api"` or search for `drone-api`.
- Metrics/Prometheus or Mimir: search metric names starting with `drone_` or `drone.` depending on OTLP-to-Prometheus conversion.

Useful signals:

- `drone.mavlink.command_latency_ms`
- `drone.ros.messages`
- `drone.mapping.chunks_saved`
- `drone.video.inference_latency_ms`
- `drone.api.websocket_messages`

## Troubleshooting

If traces, logs, and sessions are empty:

1. Confirm dependencies are installed:
   ```bash
   .venv/bin/python -m pip install -r requirements.txt -r backend/requirements.txt
   make check-local-tools
   ```
2. Confirm backend configured OpenTelemetry:
   ```bash
   rg "OpenTelemetry configured|OpenTelemetry log export configured" backend/storage/logs -S
   ```
3. Confirm endpoint and headers:
   ```bash
   echo "$OTEL_EXPORTER_OTLP_ENDPOINT"
   echo "$OTEL_EXPORTER_OTLP_HEADERS"
   ```
4. Trigger activity:
   ```bash
   curl http://localhost:8000/healthz
   ```
