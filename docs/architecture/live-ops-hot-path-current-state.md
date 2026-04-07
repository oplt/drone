# Live-Ops Hot Path: Current State

## Status
Current-state hot-path map

## Date
2026-03-31

## Purpose

This document draws the current live-ops hot path from vehicle input through
ingest, orchestration, persistence, websocket delivery, MQTT, alerts, and UI.

It complements:

- `docs/adr/ADR-001-canonical-live-ops-runtime-architecture.md`
- `docs/architecture/live-ops-runtime-path-inventory.md`

The point of this document is not to propose the target design. It is to show
where the current design is inconsistent in ordering, backpressure, and failure
handling so the refactor can be scoped against the real runtime path.

## Current Hot Path, As Implemented

### Hot-path map

```text
Vehicle / Autopilot
|
|-- Control-plane connection
|   `-- backend/drone/mavlink_drone.py (DroneKit vehicle)
|       `-- backend/drone/orchestrator.py
|           |-- create_flight() --------------------------------------> flights
|           |-- add_event() ------------------------------------------> flight_events
|           |-- start_telemetry_stream() ------------------------------+
|           |-- telemetry_publish_task() ------------------------------+
|           `-- mqtt_subscriber_task() / _raw_event_ingest_worker() ---+
|
|-- Telemetry reader A [O1][B1][F1]
|   `-- backend/messaging/websocket.py telemetry_worker
|       `-- _process_mavlink_message()
|           |-- update telemetry_manager.last_telemetry [O2]
|           |-- coalesce updates every 0.1s [O3][B2]
|           |-- per-client websocket queues (maxsize=10) [B3]
|           |   `-- /ws/telemetry
|           |       `-- frontend/src/hooks/useTelemetryWebsocket.ts
|           |           `-- UI dashboards, mission pages, alert center
|           |
|           |-- backend/services/alerts/engine.py reads last_telemetry [O4][F2]
|           |   |-- create/touch/resolve alerts ---------------------> operational_alerts
|           |   `-- broadcast alert_event ---------------------------> /ws/telemetry
|           |
|           `-- backend/ml/patrol/pipeline.py reads last_telemetry [O5][F3]
|               |-- websocket ml_anomaly_event / ml_status ---------> /ws/telemetry
|               `-- persist anomalies -------------------------------> patrol_* tables
|
`-- Telemetry reader B [O6][F4]
    `-- backend/messaging/mqtt.py MqttPublisher
        `-- msg.to_dict() + timestamp
            `-- MQTT broker / settings.telemetry_topic
                `-- backend/messaging/mqtt.py MqttClient subscriber
                    `-- _process_raw_event()
                        `-- backend/drone/orchestrator.py _raw_event_queue
                            |-- queue maxsize=2000 [B4]
                            |-- drop-oldest on overflow [B5]
                            `-- _raw_event_ingest_worker()
                                `-- add_mavlink_events_many() -------> mavlink_event

Parallel frontend runtime path

frontend/src/hooks/useMissionStatusPolling.tsx
`-- GET /tasks/flight/status every 5s [O7][F5]
    `-- backend/api/routes/routes_flights.py
        |-- route-layer mission runtime globals
        |-- telemetry_manager.last_telemetry snapshot
        `-- orchestrator readiness / flight_id snapshot
```

## What This Diagram Shows

### 1. The browser telemetry path bypasses orchestrator-owned normalization

The operational hot path that powers the UI is:

1. Vehicle
2. `backend/messaging/websocket.py`
3. `telemetry_manager.last_telemetry`
4. websocket clients
5. alert engine and ML pipeline

The orchestrator starts the telemetry worker, but it does not own the
telemetry normalization or the downstream fan-out contract. That means the
current live telemetry path is only orchestrator-adjacent, not orchestrator-led.

### 2. Raw event persistence follows a different ingest path than browser telemetry

The raw event persistence path is:

1. Vehicle
2. `backend/messaging/mqtt.py` `MqttPublisher`
3. MQTT broker
4. `backend/messaging/mqtt.py` `MqttClient`
5. `Orchestrator._raw_event_queue`
6. `TelemetryRepository.add_mavlink_events_many()`

This means the `mavlink_event` table is not fed by the same ingest path that
updates the browser, alert engine, or ML telemetry context.

### 3. Frontend live state is split between polling and websocket telemetry

The frontend combines:

- websocket telemetry from `/ws/telemetry`
- polled mission status from `/tasks/flight/status`

Those two sources are assembled separately on the backend and merged client-side.

## Inconsistency Markers

### Ordering inconsistencies

- `[O1]` Duplicate vehicle readers
  - `backend/messaging/websocket.py` and `backend/messaging/mqtt.py` each read
    live MAVLink traffic independently.
  - Result: there is no shared sequencing guarantee between UI telemetry and raw
    DB events.

- `[O2]` Shared telemetry state is snapshot-based, not envelope-based
  - `telemetry_manager.last_telemetry` is a mutable merged snapshot.
  - Result: consumers do not observe a stable ordered event stream.

- `[O3]` Websocket delivery coalesces updates
  - The telemetry worker merges buffered messages at roughly 10 Hz before
    broadcast.
  - Result: intermediate message order is intentionally collapsed for the UI
    path, but not for the raw-event path.

- `[O4]` Alerts consume periodic snapshots, not ordered telemetry events
  - `AlertEngine` reads `last_telemetry` on a timer.
  - Result: alert evaluation order is based on polling cadence, not the actual
    order of incoming vehicle messages.

- `[O5]` ML consumes frame-time telemetry snapshots, not synchronized envelopes
  - The patrol pipeline asks for "latest" telemetry when a frame is processed.
  - Result: telemetry-to-frame alignment is best effort and can drift under
    load or reconnects.

- `[O6]` MQTT raw persistence only sees the subset emitted by `MqttPublisher`
  - The publisher filters message types before publishing.
  - Result: the persisted raw-event stream is neither complete nor guaranteed to
    match the telemetry worker's observed message sequence.

- `[O7]` Mission status ordering is separate from telemetry ordering
  - `/tasks/flight/status` assembles route-layer runtime state plus a
    telemetry snapshot every 5 seconds.
  - Result: the browser can observe fresh websocket telemetry with stale mission
    runtime or fresh mission runtime with stale telemetry.

### Backpressure inconsistencies

- `[B1]` Websocket ingest has no shared queue before state mutation
  - The telemetry worker updates `last_telemetry` directly after each MAVLink
    message.
  - Result: there is no single bounded ingest point controlling flow before
    downstream consumers observe the state.

- `[B2]` Websocket broadcast path coalesces instead of preserving every update
  - Message buffering plus 10 Hz broadcast acts as an implicit pressure valve.
  - Result: UI subscribers receive a reduced stream, but this policy is local to
    websocket telemetry and not shared with other consumers.

- `[B3]` Per-client websocket buffers drop oldest messages
  - Client queues in `telemetry_manager.connect()` use `maxsize=10`.
  - `_enqueue_latest()` removes the oldest queued payload when full.
  - Result: each client may observe a different subsequence during load.

- `[B4]` Raw-event persistence uses a bounded queue independent of websocket flow
  - `Orchestrator._raw_event_queue` uses `maxsize=2000`.
  - Result: DB ingest pressure is isolated from websocket pressure, so the two
    paths degrade differently.

- `[B5]` Raw-event queue overflow also drops oldest
  - `MqttClient._process_raw_event()` drops the oldest raw event when the queue
    is full.
  - Result: persistence loses history under pressure with no relation to what
    the browser already saw.

- `[B6]` Alerts and ML have no explicit backpressure contract
  - Alerts poll a shared snapshot.
  - ML reads the latest available telemetry at frame-processing time.
  - Result: both consumers silently skip intermediate state rather than applying
    a declared queue or sampling policy.

### Failure-handling inconsistencies

- `[F1]` Telemetry websocket worker is a single hidden dependency for multiple systems
  - If `backend/messaging/websocket.py` stops, reconnects badly, or falls behind,
    the UI, alert engine, ML telemetry context, analytics health, and flight
    status snapshots all degrade together.

- `[F2]` Alert engine failure scope is indirect
  - Alert logic does not fail because the vehicle path failed directly; it fails
    because its dependency on `last_telemetry` went stale or absent.
  - Result: alert correctness depends on websocket telemetry health, not on an
    explicit alert input contract.

- `[F3]` ML runtime failure scope is indirect
  - ML frame processing can continue while telemetry context is stale, missing,
    or lagging.
  - Result: detections may persist with degraded or absent geo context without a
    shared runtime error boundary.

- `[F4]` MQTT failure breaks DB raw-event persistence without breaking the UI
  - If `MqttPublisher`, the broker, or `MqttClient` fails, `mavlink_event`
    writes stop, but websocket telemetry can continue.
  - Result: UI and persistence disagree about what "the current flight stream"
    means.

- `[F5]` Mission status has split runtime ownership
  - Telemetry can be started or stopped by orchestrator mission startup and also
    by `/tasks/telemetry/start` and `/tasks/telemetry/stop`.
  - Mission status is assembled in `routes_flights.py` from route globals and a
    telemetry snapshot.
  - Result: startup, shutdown, and restart behavior are not owned by one runtime
    component.

- `[F6]` Telemetry persistence code exists but is not on the hot path
  - `TelemetryRepository.add_telemetry()` and `add_telemetry_many()` are not the
    active live ingest path.
  - Result: a telemetry DB write failure today is mostly irrelevant because the
    live telemetry path does not depend on it, while raw-event persistence
    failure is isolated to the MQTT branch.

## Current Hot-Path Conclusions

1. There is no single hot path today. There are two telemetry hot paths plus a
   separate control path.
2. The orchestrator controls mission lifecycle, but not the main telemetry
   normalization contract consumed by the rest of the system.
3. Ordering is inconsistent because UI telemetry, raw DB events, alerts, ML,
   and mission status are all derived from different timing models.
4. Backpressure is inconsistent because websocket delivery, MQTT raw-event
   ingestion, alerts, and ML each apply a different implicit sampling or drop
   strategy.
5. Failure handling is inconsistent because websocket telemetry failure, MQTT
   failure, and route-layer mission runtime failure affect different downstream
   systems in different ways.

## Refactor Implication

The first refactor step should not start at the UI. It should start where the
current hot path forks:

1. one ingest owner
2. one normalized runtime envelope
3. one explicit backpressure policy per consumer
4. one mission runtime owner

Until those exist, every downstream improvement to alerts, replay, telemetry
charts, or fleet UX will still inherit the current path inconsistencies.
