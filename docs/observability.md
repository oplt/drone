# Drone Observability

The backend exports standard OpenTelemetry traces over OTLP/HTTP and
Prometheus metrics from `/metrics`.

Local development defaults:

- Grafana UI: `http://127.0.0.1:3000`
- Tempo query/readiness: `http://127.0.0.1:3200`
- Tempo OTLP/HTTP ingest: `http://127.0.0.1:4318`
- Prometheus: `http://127.0.0.1:9090`
- App metrics: `http://127.0.0.1:8000/metrics`

Maple is optional and disabled by default. `make local-dev` no longer starts or
requires Maple; `make start-maple MAPLE_ENABLED=1` is kept only for explicit
legacy use.

For local Grafana, Prometheus, and Tempo setup, see
`docs/local-observability.md`.

## Runtime Config

```bash
export OBSERVABILITY_ENABLED=true
export OTEL_SERVICE_NAME=drone-api
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
export OTEL_TRACES_EXPORTER=otlp
export OTEL_METRICS_EXPORTER=none
export PROMETHEUS_METRICS_ENABLED=true
export PROMETHEUS_METRICS_PATH=/metrics
```

Disable local observability:

```bash
make local-dev-no-observability
```

Run with explicit observability defaults:

```bash
make local-dev-observability
```

## Exported Signals

Traces:

- FastAPI requests via automatic instrumentation.
- MAVLink control spans.
- ROS/Gazebo point-cloud callback spans.
- Mapping spans for chunk generation, save, load, replay, and websocket publish.
- Video spans for metadata read, inference, detection storage, upload, and
  analysis start.
- Mapping stack start/stop spans.

Prometheus metrics:

- HTTP request count, latency, status codes, and unhandled exceptions.
- Drone workflow counters/gauges in `backend/observability/prometheus_metrics.py`,
  including active drone connections, mission command counts, telemetry message
  counts, telemetry lag, video analysis jobs, Celery task duration, and Redis
  queue depth.

Application OpenTelemetry helper metrics:

- `drone.mavlink.command_latency_ms`
- `drone.mavlink.command_failures`
- `drone.mavlink.command_retries`
- `drone.mavlink.ack_timeouts`
- `drone.ros.messages`
- `drone.ros.callback_latency_ms`
- `drone.ros.topic_stale`
- `drone.ros.message_size_bytes`
- `drone.mapping.frames_received`
- `drone.mapping.pointclouds_received`
- `drone.mapping.chunks_generated`
- `drone.mapping.chunks_saved`
- `drone.mapping.chunk_save_failures`
- `drone.mapping.chunk_save_latency_ms`
- `drone.mapping.replay_latency_ms`
- `drone.video.frames_received`
- `drone.video.frames_processed`
- `drone.video.frames_dropped`
- `drone.video.inference_latency_ms`
- `drone.video.detection_count`
- `drone.api.websocket_messages`
- `drone.api.websocket_disconnects`
- `drone.api.request_failures`

Logs:

- JSON/text logs include `service_name`, `environment`, `otel_trace_id`, and
  `otel_span_id` when a request span is active.
- Structured failures include bounded fields such as `mission_id`, `flight_id`,
  `frame_id`, `ros_topic`, `map_id`, `chunk_id`, `mavlink_command`,
  `error_type`, and `error_message`.

## Safety

Tempo, Prometheus, and Grafana are external local services. If any are down, the
FastAPI app still starts. OTLP export failures are handled by OpenTelemetry
batch processors and must not affect control, mapping, or video code paths.
